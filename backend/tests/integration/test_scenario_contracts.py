from datetime import UTC, datetime, timedelta, tzinfo
from functools import partial
from typing import Any

import pytest
from fsrs import Rating
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError
from app.db import llm as cache
from app.domain.exercises import AttemptCreate, AttemptGraded, Unavailable
from app.domain.jobs import Job
from app.domain.user_dictionary import CustomSenseCreate
from app.services import exercise_attempts as attempts
from app.services import jobs, scenario, srs, user_dictionary
from app.services.exercise_registry import ExerciseRegistry
from app.services.exercise_scenario import register
from app.services.lexicon import LexiconReader
from app.worker.runtime import execute
from tests.conftest import UserFactory
from tests.integration.srs_support import create_study, graded
from tests.llm_support import provider as provider
from tests.scenario_support import TEXT, claim_scenario, study_context
from tests.scenario_support import db as db
from tests.scenario_support import scheduled as scheduled
from tests.scenario_support import settings as settings

pytestmark = pytest.mark.integration


async def test_failed_generation_can_recover_next_utc_day(
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
    provider["content"] = "invalid JSON"
    await scenario.acquire(job_db, settings, context)
    await execute(job_db, await claim_scenario(job_db), settings=settings)
    first = scheduled[-1].id
    assert await scenario.acquire(job_db, settings, context) == Unavailable(
        exercise="scenario", reason="invalid_response"
    )

    class Tomorrow(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return datetime.now(tz or UTC) + timedelta(days=1)

    monkeypatch.setattr(scenario, "datetime", Tomorrow)
    provider["content"] = '{"scenario":"' + TEXT + '"}'
    assert await scenario.acquire(job_db, settings, context) == Unavailable(
        exercise="scenario", reason="generation_pending"
    )
    assert scheduled[-1].id != first
    await execute(job_db, await claim_scenario(job_db), settings=settings)
    assert not isinstance(await scenario.acquire(job_db, settings, context), Unavailable)
    assert provider["calls"] == 2


async def test_exhausted_nonzero_daily_budget_is_observable(
    job_db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    study = await create_study(job_db, make_user, lexicon_reader)
    settings = settings.model_copy(update={"llm_daily_budget": 1})
    assert await cache.reserve_attempt(job_db, study.user.id, 1)
    context = await study_context(job_db, study)
    await scenario.acquire(job_db, settings, context)
    job = await claim_scenario(job_db)
    await execute(job_db, job, settings=settings)
    assert (await jobs.read(job_db, job.id, study.user.id)).error == "budget_exhausted"
    assert await scenario.acquire(job_db, settings, context) == Unavailable(
        exercise="scenario", reason="budget_exhausted"
    )
    assert provider["calls"] == 0


async def test_custom_source_cache_never_crosses_owners(
    job_db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    study = await create_study(job_db, make_user, lexicon_reader)
    other = await create_study(job_db, make_user, lexicon_reader)
    context = await study_context(job_db, study)
    custom = await user_dictionary.create_sense(
        job_db,
        study.user.id,
        context.lexeme.id,
        CustomSenseCreate(definition="A private customized meaning"),
    )
    context = context.model_copy(update={"sense": custom, "sense_id": custom.id})
    request = await scenario._request(job_db, settings, context)
    assert not request.sources
    provider["content"] = '{"scenario":"' + TEXT + '"}'
    await scenario._generate(job_db, settings, context, request)
    disabled = settings.model_copy(update={"deepseek_api_key": ""})
    assert not isinstance(await scenario.acquire(job_db, disabled, context), Unavailable)
    foreign = context.model_copy(update={"owner": other.user.id})
    assert await scenario.acquire(job_db, disabled, foreign) == Unavailable(
        exercise="scenario", reason="invalid_scope"
    )
    # Even identical private input from a different visible owner cannot reuse the first cache.
    other_custom = custom.model_copy(update={"owner": other.user.id})
    foreign = foreign.model_copy(update={"sense": other_custom})
    assert await scenario.acquire(job_db, disabled, foreign) == Unavailable(
        exercise="scenario", reason="disabled"
    )
    assert provider["calls"] == 1


async def test_scenario_uses_durable_local_grading_ownership_and_timing(
    db: AsyncSurrealConnection,
    job_db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    assert db is job_db, "Scenario auth, cards and worker jobs must use one isolated database"
    study = await create_study(db, make_user, lexicon_reader)
    other = await make_user()
    context = await study_context(db, study)
    provider["content"] = '{"scenario":"' + TEXT + '"}'
    await scenario.acquire(db, settings, context)
    await execute(db, await claim_scenario(db), settings=settings)
    seed = await graded(db, study, exercise="offline", kind="recognition")
    await srs.apply_review(db, study.user.id, seed, Rating.Easy)
    target = ExerciseRegistry()
    register(target, partial(scenario.acquire, db, settings))
    opened = await attempts.create_attempt(
        db,
        study.user.id,
        AttemptCreate(project_id=study.project.id, sense_id=study.sense_id),
        plugins=target,
    )
    assert opened.exercise == "scenario" and opened.kind == "recall"
    assert opened.prompt.text == TEXT
    assert "accepted_forms" not in opened.model_dump_json()
    for action in (
        attempts.read_attempt(db, other.id, opened.id),
        attempts.submit(db, settings, other.id, opened.id, "ran", 100, plugins=target),
    ):
        with pytest.raises(AppError) as caught:
            await action
        assert caught.value.status == 404
    result = await attempts.submit(
        db,
        settings,
        study.user.id,
        opened.id,
        " ＲＡＮ ",
        120000,
        plugins=target,
    )
    assert isinstance(result, AttemptGraded) and result.feedback.correct
    assert result.duration_ms == min(result.server_elapsed_ms, 60000)
    assert provider["calls"] == 1
    confirmed = await attempts.confirm(db, study.user.id, opened.id, Rating.Good)
    assert confirmed.status == "confirmed"
    assert await attempts.confirm(db, study.user.id, opened.id, Rating.Good) == confirmed
