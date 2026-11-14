import asyncio
from typing import Any

import pytest
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.domain.exercises import ScenarioSource, Unavailable
from app.domain.jobs import Job
from app.domain.notes import NoteCreate
from app.domain.overrides import OverrideFields, OverrideUpdate
from app.services import jobs, notes, overrides, scenario
from app.services.lexicon import LexiconReader
from app.worker.runtime import execute, run_once
from tests.conftest import UserFactory
from tests.integration.srs_support import create_study
from tests.llm_support import provider as provider
from tests.scenario_support import TEXT, claim_scenario, study_context
from tests.scenario_support import scheduled as scheduled
from tests.scenario_support import settings as settings

pytestmark = pytest.mark.integration


async def test_nonblocking_concurrent_misses_one_job_and_disabled_shared_cache(
    job_db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    settings: Settings,
    provider: dict[str, Any],
    scheduled: list[Job],
) -> None:
    study = await create_study(job_db, make_user, lexicon_reader)
    other = await create_study(job_db, make_user, lexicon_reader)
    for selected, text in ((study, "own-private-note"), (other, "other-private-note")):
        await notes.create(
            job_db,
            selected.user.id,
            NoteCreate(target_table="sense", target_id=selected.sense_id, text=text),
        )
    context = await study_context(job_db, study)
    while pending := await jobs.claim(job_db):
        await jobs.complete(job_db, pending)
    provider["content"] = '{"scenario":"' + TEXT + '"}'
    provider["sleep"] = True
    results = await asyncio.gather(*(scenario.acquire(job_db, settings, context) for _ in range(6)))
    assert all(
        isinstance(item, Unavailable) and item.reason == "generation_pending" for item in results
    )
    assert provider["calls"] == 0
    assert len({job.id for job in scheduled}) == 1
    assert set(scheduled[0].payload) == {"project_id", "sense_id", "key"}
    workers = await asyncio.gather(
        run_once(job_db, settings=settings), run_once(job_db, settings=settings)
    )
    assert sum(workers) == 1
    assert (await jobs.read(job_db, scheduled[0].id, study.user.id)).status == "done"
    assert provider["calls"] == 1
    assert b"private-note" not in provider["request"].content
    disabled = settings.model_copy(update={"deepseek_api_key": "", "llm_daily_budget": 0})
    assert isinstance(await scenario.acquire(job_db, disabled, context), ScenarioSource)
    assert isinstance(
        await scenario.acquire(job_db, disabled, await study_context(job_db, other)), ScenarioSource
    )
    assert provider["calls"] == 1


@pytest.mark.parametrize(
    "content,reason",
    [
        ("not JSON", "invalid_response"),
        ('{"scenario":"too short"}', "invalid_response"),
        ('{"scenario":"She runs and is running to catch the bus."}', "rejected_response"),
        ('{"scenario":"She has RAN across the road to catch her bus."}', "rejected_response"),
        ('{"scenario":"' + TEXT + '","answer":"run"}', "invalid_response"),
    ],
)
async def test_invalid_provider_output_never_cached_and_terminal_job_reused(
    job_db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    settings: Settings,
    provider: dict[str, Any],
    scheduled: list[Job],
    content: str,
    reason: str,
) -> None:
    study = await create_study(job_db, make_user, lexicon_reader)
    context = await study_context(job_db, study)
    provider["content"] = content
    await scenario.acquire(job_db, settings, context)
    job = await claim_scenario(job_db)
    await execute(job_db, job, settings=settings)
    status = await jobs.read(job_db, job.id, study.user.id)
    assert status.status == "failed" and status.error == reason
    assert (await scenario.acquire(job_db, settings, context)) == Unavailable(
        exercise="scenario", reason=reason
    )
    assert len({job.id for job in scheduled}) == 1 and provider["calls"] == 1


@pytest.mark.parametrize(
    "change,provider_change,reason",
    [
        ({"deepseek_api_key": ""}, {}, "disabled"),
        ({"deepseek_api_key": "sk-example"}, {}, "disabled"),
        ({"llm_daily_budget": 0}, {}, "budget_exhausted"),
        ({}, {"error": True}, "provider_error"),
        ({"llm_timeout_seconds": 0.01}, {"sleep": True}, "timeout"),
        ({}, {"status": 429}, "provider_error"),
    ],
)
async def test_all_optional_provider_fallbacks(
    job_db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    settings: Settings,
    provider: dict[str, Any],
    scheduled: list[Job],
    change: dict[str, Any],
    provider_change: dict[str, Any],
    reason: str,
) -> None:
    study = await create_study(job_db, make_user, lexicon_reader)
    context = await study_context(job_db, study)
    settings = settings.model_copy(update=change)
    provider.update(provider_change)
    result = await scenario.acquire(job_db, settings, context)
    if scheduled:
        await execute(job_db, await claim_scenario(job_db), settings=settings)
        result = await scenario.acquire(job_db, settings, context)
    assert result == Unavailable(exercise="scenario", reason=reason)
    if reason in {"disabled", "budget_exhausted"}:
        assert provider["calls"] == 0


async def test_versions_invalidate_cache_and_jobs(
    job_db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    settings: Settings,
    provider: dict[str, Any],
    scheduled: list[Job],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = await create_study(job_db, make_user, lexicon_reader)
    context = await study_context(job_db, study)
    provider["content"] = '{"scenario":"' + TEXT + '"}'
    await scenario.acquire(job_db, settings, context)
    await execute(job_db, await claim_scenario(job_db), settings=settings)
    first = scheduled[-1].id
    monkeypatch.setattr(scenario, "PROMPT_VERSION", "scenario-v2")
    assert isinstance(await scenario.acquire(job_db, settings, context), Unavailable)
    assert scheduled[-1].id != first
    await execute(job_db, await claim_scenario(job_db), settings=settings)
    assert isinstance(await scenario.acquire(job_db, settings, context), ScenarioSource)
    assert provider["calls"] == 2


async def test_effective_overlay_is_private_and_never_sent_to_shared_cache(
    job_db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    first = await create_study(job_db, make_user, lexicon_reader)
    second = await create_study(job_db, make_user, lexicon_reader)
    await overrides.write(
        job_db,
        first.user.id,
        "sense",
        first.sense_id,
        OverrideUpdate(fields=OverrideFields(definition="Private selected sense definition")),
        action="patch",
    )
    context = await study_context(job_db, first)
    provider["content"] = '{"scenario":"' + TEXT + '"}'
    await scenario.acquire(job_db, settings, context)
    await execute(job_db, await claim_scenario(job_db), settings=settings)
    request = provider["request"].content
    assert b"Private selected sense definition" in request
    disabled = settings.model_copy(update={"deepseek_api_key": ""})
    assert isinstance(await scenario.acquire(job_db, disabled, context), ScenarioSource)
    assert await scenario.acquire(
        job_db, disabled, await study_context(job_db, second)
    ) == Unavailable(exercise="scenario", reason="disabled")


async def test_worker_rechecks_content_before_provider_dispatch(
    job_db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    study = await create_study(job_db, make_user, lexicon_reader)
    context = await study_context(job_db, study)
    await scenario.acquire(job_db, settings, context)
    await overrides.write(
        job_db,
        study.user.id,
        "sense",
        study.sense_id,
        OverrideUpdate(fields=OverrideFields(definition="Changed after enqueue")),
        action="patch",
    )
    job = await claim_scenario(job_db)
    await execute(job_db, job, settings=settings)
    assert (await jobs.read(job_db, job.id, study.user.id)).error == "stale_content"
    assert provider["calls"] == 0
