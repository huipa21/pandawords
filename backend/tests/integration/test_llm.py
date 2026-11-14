import asyncio
import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel
from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.core.errors import LlmUnavailable
from app.db import llm as repository
from app.db.auth import _rows
from app.domain.identity import user_subject
from tests.llm_support import Answer, generate
from tests.llm_support import provider as provider
from tests.llm_support import settings as settings


async def test_valid_persistent_canonical_cache_disabled(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    user = user_subject("llm_" + uuid4().hex)
    first = await generate(job_db, settings, user=user, inputs={"a": 1, "b": 2})
    second = await generate(
        job_db,
        settings.model_copy(update={"deepseek_api_key": ""}),
        user=user,
        inputs={"b": 2, "a": 1},
    )
    assert first.value.text == "valid" and not first.cached
    assert second.cached and provider["calls"] == 1
    assert (
        await generate(
            job_db,
            settings.model_copy(update={"llm_daily_budget": 0}),
            user=user,
            inputs={"a": 1, "b": 2},
        )
    ).cached
    request = provider["request"]
    assert b'"json_object"' in request.content


@pytest.mark.parametrize(
    "change",
    [
        {"prompt_version": "v2"},
        {"schema_version": "v2"},
        {"prompt": "Different JSON prompt"},
        {"inputs": {"note": "changed"}},
        {"model": "deepseek-reasoner"},
    ],
)
async def test_cache_versioning(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
    change: dict[str, Any],
) -> None:
    user = user_subject("llm_" + uuid4().hex)
    await generate(job_db, settings, user=user)
    if "model" in change:
        settings = settings.model_copy(update={"deepseek_model": change["model"]})
        change = {}
    result = await generate(job_db, settings, user=user, **change)
    assert not result.cached and provider["calls"] == 2


async def test_actual_schema_also_versions_cache(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    class ExtendedAnswer(Answer):
        explanation: str

    user = user_subject("llm_" + uuid4().hex)
    await generate(job_db, settings, user=user)
    provider["content"] = '{"text":"valid","explanation":"new schema"}'
    result = await generate(job_db, settings, user=user, response_model=ExtendedAnswer)
    assert result.value.explanation == "new schema" and provider["calls"] == 2


@pytest.mark.parametrize(
    "key", ["", " ", "replace-with-your-api-key", "sk-example", "YOUR_API_KEY"]
)
async def test_disabled(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
    key: str,
) -> None:
    with pytest.raises(LlmUnavailable) as error:
        await generate(job_db, settings.model_copy(update={"deepseek_api_key": key}))
    assert error.value.reason == "disabled" and provider["calls"] == 0


@pytest.mark.parametrize("content", ["not json", '{"text":4}', '{"text":"x","extra":1}', "null"])
async def test_invalid_never_cached(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
    content: str,
) -> None:
    user = user_subject("llm_" + uuid4().hex)
    provider["content"] = content
    with pytest.raises(LlmUnavailable) as error:
        await generate(job_db, settings, user=user)
    assert error.value.reason == "invalid_response"
    provider["content"] = '{"text":"valid"}'
    assert not (await generate(job_db, settings, user=user)).cached
    assert provider["calls"] == 2


async def test_caller_rejection_and_cached_validation(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    user = user_subject("llm_" + uuid4().hex)
    with pytest.raises(LlmUnavailable, match="unavailable") as error:
        await generate(job_db, settings, user=user, validate=lambda value: False)
    assert error.value.reason == "rejected_response"
    assert not (await generate(job_db, settings, user=user)).cached
    with pytest.raises(LlmUnavailable):
        await generate(job_db, settings, user=user, validate=lambda value: False)
    assert provider["calls"] == 2


@pytest.mark.parametrize("constant", ["NaN", "Infinity"])
async def test_nonstandard_json_numbers_rejected(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
    constant: str,
) -> None:
    class NumericAnswer(BaseModel):
        value: float

    provider["content"] = '{"value":' + constant + "}"
    with pytest.raises(LlmUnavailable) as error:
        await generate(job_db, settings, response_model=NumericAnswer)
    assert error.value.reason == "invalid_response"


@pytest.mark.parametrize(
    ("options", "reason", "calls"),
    [
        ({"status": 401}, "provider_error", 1),
        ({"status": 500}, "provider_error", 2),
        ({"error": True}, "provider_error", 2),
        ({"sleep": True}, "timeout", 2),
        ({"finish": "length"}, "invalid_response", 1),
    ],
)
async def test_failures_consume_retry_budget_and_log_hygiene(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    options: dict[str, Any],
    reason: str,
    calls: int,
) -> None:
    settings = settings.model_copy(update={"llm_max_retries": 1, "llm_daily_budget": calls})
    if options.get("sleep"):
        settings = settings.model_copy(update={"llm_timeout_seconds": 0.05})
    user = user_subject("llm_" + uuid4().hex)
    provider.update(options)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(LlmUnavailable) as error:
        await generate(job_db, settings, user=user)
    assert error.value.reason == reason and provider["calls"] == calls
    with pytest.raises(LlmUnavailable) as exhausted:
        await generate(job_db, settings, user=user)
    assert exhausted.value.reason == "budget_exhausted" and provider["calls"] == calls
    assert "sk-test-secret" not in caplog.text and "private-note" not in caplog.text


async def test_zero_budget_and_retry_reservation(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    with pytest.raises(LlmUnavailable) as error:
        await generate(job_db, settings.model_copy(update={"llm_daily_budget": 0}))
    assert error.value.reason == "budget_exhausted" and provider["calls"] == 0
    provider["status"] = 500
    with pytest.raises(LlmUnavailable) as error:
        await generate(
            job_db,
            settings.model_copy(update={"llm_daily_budget": 1, "llm_max_retries": 3}),
        )
    assert error.value.reason == "budget_exhausted" and provider["calls"] == 1


async def test_atomic_budget_concurrency_utc_reset_and_isolation(
    job_db: AsyncSurrealConnection,
) -> None:
    user = user_subject("llm_" + uuid4().hex)
    day = datetime(2026, 11, 14, 23, 59, tzinfo=UTC)
    reservations = await asyncio.gather(
        *[repository.reserve_attempt(job_db, user, 3, now=day) for _ in range(8)]
    )
    assert sum(reservations) == 3
    assert not await repository.reserve_attempt(job_db, user, 3, now=day)
    same_day_offset = day.astimezone(timezone(timedelta(hours=8)))
    assert not await repository.reserve_attempt(job_db, user, 3, now=same_day_offset)
    assert await repository.reserve_attempt(job_db, user, 3, now=day + timedelta(minutes=1))
    assert await repository.reserve_attempt(
        job_db, user_subject("other_" + uuid4().hex), 3, now=day
    )


async def test_concurrent_dispatches_never_exceed_budget(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    user = user_subject("llm_" + uuid4().hex)
    settings = settings.model_copy(update={"llm_daily_budget": 3})
    results = await asyncio.gather(
        *[generate(job_db, settings, user=user, inputs={"index": index}) for index in range(8)],
        return_exceptions=True,
    )
    assert provider["calls"] == 3
    assert sum(not isinstance(result, Exception) for result in results) == 3
    assert all(
        not isinstance(result, Exception)
        or isinstance(result, LlmUnavailable)
        and result.reason == "budget_exhausted"
        for result in results
    )


async def test_shared_owner_cache_isolation(
    job_db: AsyncSurrealConnection,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    alice = user_subject("alice_" + uuid4().hex)
    bob = user_subject("bob_" + uuid4().hex)
    await generate(job_db, settings, user=alice)
    assert not (await generate(job_db, settings, user=bob)).cached
    sense = RecordID("sense", "llm_" + uuid4().hex)
    await _rows(
        job_db,
        "CREATE $id CONTENT $data;",
        {
            "id": sense,
            "data": {
                "definition": "shared definition",
                "gloss": {},
                "register": [],
                "domain": [],
                "examples": [],
                "rank": 1,
                "common": True,
                "source": "test",
                "owner": None,
            },
        },
    )
    assert not (
        await generate(job_db, settings, user=alice, inputs=None, shared_sources=(sense,))
    ).cached
    assert (
        await generate(
            job_db,
            settings.model_copy(update={"deepseek_api_key": ""}),
            user=bob,
            inputs=None,
            shared_sources=(sense,),
        )
    ).cached
    with pytest.raises(LlmUnavailable) as error:
        await generate(job_db, settings, shared_sources=(sense,))
    assert error.value.reason == "invalid_scope"
    await _rows(
        job_db,
        "UPDATE $id SET owner = $owner;",
        {
            "id": sense,
            "owner": repository.owner_record(alice),
        },
    )
    with pytest.raises(LlmUnavailable) as error:
        await generate(job_db, settings, user=bob, inputs=None, shared_sources=(sense,))
    assert error.value.reason == "invalid_scope" and provider["calls"] == 3
