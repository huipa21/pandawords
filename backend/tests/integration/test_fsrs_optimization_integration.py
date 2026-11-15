import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fsrs import Rating, Scheduler
from fsrs.scheduler import DEFAULT_PARAMETERS
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db import srs_optimization as repository
from app.db.auth import find_user
from app.db.memory_schema_test_support import owned
from app.db.srs import user_record
from app.db.srs_optimization_test_support import replace_parameters, seed, set_preferences
from app.domain.auth import UserPreferences
from app.domain.srs_optimization import MAX_FETCHED_LOGS, OPTIMIZER_VERSION, OptimizationRead
from app.services import srs, srs_optimization
from app.services.lexicon import LexiconReader
from app.services.srs_optimization_history import training_history
from tests.conftest import UserFactory
from tests.integration.srs_support import create_study, graded
from tests.srs_optimization_support import history

pytestmark = pytest.mark.integration


async def store_parameters(
    db: AsyncWsSurrealConnection, owner: str, now: datetime, values: list[float]
) -> None:
    run = await repository.claim(db, owner, now)
    assert run is not None
    result = OptimizationRead(
        status="success", at=now, eligible_reviews=512, history_fingerprint="a" * 64
    )
    assert await repository.finish(db, owner, run, result, values)


async def test_success_uses_only_owner_history_and_preserves_existing_data(
    db: AsyncWsSurrealConnection, make_user: UserFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, other = await make_user(), await make_user()
    now = datetime.now(UTC)
    prefs = UserPreferences(
        theme="dark",
        locale="en",
        accent="UK",
        desired_retention=0.96,
        review_audio_enabled=False,
        review_images_enabled=False,
    )
    await set_preferences(db, user.id, prefs)
    own_rows = history(user.id, cards=16, reviews=33, start=now - timedelta(days=100))
    foreign_rows = history(
        other.id, cards=16, reviews=33, start=now - timedelta(days=100), inverted=True
    )
    await seed(db, own_rows)
    await seed(db, foreign_rows)
    before_cards = await owned(db, "memory", user_record(user.id))
    before_logs = await owned(db, "review_log", user_record(user.id))
    foreign_cards = await owned(db, "memory", user_record(other.id))
    foreign_logs = await owned(db, "review_log", user_record(other.id))
    expected, _ = training_history(own_rows, user.id, now)
    values = list(DEFAULT_PARAMETERS)
    values[0] = 1.0
    calls = 0

    async def compute(logs: list[dict[str, Any]]) -> tuple[str, object]:
        nonlocal calls
        calls += 1
        assert logs == expected and len(logs) == 528
        return "success", values

    monkeypatch.setattr(srs_optimization, "compute", compute)
    result = await srs_optimization.optimize(db, user.id, now=now)
    assert result.status == "success" and result.eligible_reviews == 512
    assert await srs_optimization.optimize(db, user.id, now=now) == result and calls == 1
    assert await srs_optimization.read(db, user.id) == result
    assert (await srs_optimization.read(db, other.id)).status == "not_run"
    row = await repository.state(db, user.id)
    assert row["parameters"] == values and row["parameters_version"] == OPTIMIZER_VERSION
    assert row["optimized_at"] == now and row["trained_reviews"] == 512
    assert row["parameters_fingerprint"] == result.history_fingerprint
    assert await owned(db, "memory", user_record(user.id)) == before_cards
    assert await owned(db, "review_log", user_record(user.id)) == before_logs
    assert await owned(db, "memory", user_record(other.id)) == foreign_cards
    assert await owned(db, "review_log", user_record(other.id)) == foreign_logs
    loaded = await find_user(db, user.id)
    assert loaded is not None and loaded.prefs == prefs


async def test_reoptimization_requires_cooldown_and_new_eligible_transitions(
    db: AsyncWsSurrealConnection, make_user: UserFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user()
    now = datetime.now(UTC)
    all_rows = history(
        user.id, cards=16, reviews=40, start=now - timedelta(days=32), interval=timedelta(days=1)
    )
    rows = [row for row in all_rows if row["at"] <= now]
    calls = 0

    async def get_history(*args: Any) -> list[dict[str, Any]]:
        return rows

    async def compute(*args: Any) -> tuple[str, object]:
        nonlocal calls
        calls += 1
        values = list(DEFAULT_PARAMETERS)
        values[0] = float(calls)
        return "success", values

    monkeypatch.setattr(repository, "history", get_history)
    monkeypatch.setattr(srs_optimization, "compute", compute)
    first = await srs_optimization.optimize(db, user.id, now=now)
    assert first.status == "success" and calls == 1
    assert await srs_optimization.optimize(db, user.id, now=now + timedelta(days=29)) == first
    unchanged = await srs_optimization.optimize(db, user.id, now=now + timedelta(days=30))
    assert (unchanged.status, unchanged.reason) == ("insufficient_history", "minimum_new_history")
    assert (await repository.state(db, user.id))["parameters"][0] == 1.0
    rows = all_rows
    retrained = await srs_optimization.optimize(db, user.id, now=now + timedelta(days=32))
    assert retrained.status == "success" and retrained.eligible_reviews == 624 and calls == 2
    assert (await repository.state(db, user.id))["parameters"][0] == 2.0


async def test_mature_cards_can_retrain_after_the_history_window_fills(
    db: AsyncWsSurrealConnection, make_user: UserFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user()
    now = datetime.now(UTC)
    rows = history(
        user.id, cards=16, reviews=80, start=now - timedelta(days=69), interval=timedelta(days=1)
    )
    await seed(db, [row for row in rows if row["at"] <= now])
    calls = 0

    async def compute(*args: Any) -> tuple[str, object]:
        nonlocal calls
        calls += 1
        return "success", list(DEFAULT_PARAMETERS)

    monkeypatch.setattr(srs_optimization, "compute", compute)
    first = await srs_optimization.optimize(db, user.id, now=now)
    assert first.status == "success" and first.eligible_reviews == 1008 and calls == 1
    await seed(db, [row for row in rows if row["at"] > now])
    second = await srs_optimization.optimize(db, user.id, now=now + timedelta(days=30))
    assert second.status == "success" and second.eligible_reviews == 1008 and calls == 2
    assert second.history_fingerprint != first.history_fingerprint


async def test_global_history_horizon_bounds_even_a_dominant_card(
    db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    user = await make_user()
    now = datetime.now(UTC)
    recent = history(
        user.id,
        cards=1,
        reviews=MAX_FETCHED_LOGS,
        start=now - timedelta(hours=2),
        interval=timedelta(seconds=1),
    )
    older = history(user.id, cards=2, reviews=2, start=now - timedelta(days=200))[2:]
    await seed(db, [*older, *recent])
    rows = await repository.history(db, user.id)
    assert len(rows) == 65
    assert {str(row["memory"]) for row in rows} == {str(recent[0]["memory"])}


@pytest.mark.parametrize("outcome", ["failed", "unavailable", "invalid", "exception"])
async def test_failure_preserves_prior_valid_parameters_and_metadata(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    user = await make_user()
    now = datetime.now(UTC)
    values = list(DEFAULT_PARAMETERS)
    values[0] = 1.0
    await store_parameters(db, user.id, now - timedelta(days=31), values)
    previous = await repository.state(db, user.id)
    rows = history(
        user.id, cards=16, reviews=33, start=now - timedelta(days=35), interval=timedelta(days=1)
    )

    async def get_history(*args: Any) -> list[dict[str, Any]]:
        return rows

    async def compute(*args: Any) -> tuple[str, object]:
        if outcome == "exception":
            raise RuntimeError("private failure")
        return ("success", [float("nan")] * 21) if outcome == "invalid" else (outcome, None)

    monkeypatch.setattr(repository, "history", get_history)
    monkeypatch.setattr(srs_optimization, "compute", compute)
    result = await srs_optimization.optimize(db, user.id, now=now)
    assert result.status == ("unavailable" if outcome == "unavailable" else "failed")
    assert await srs_optimization.read(db, user.id) == result
    assert "private" not in result.model_dump_json()
    assert await srs_optimization.optimize(db, user.id, now=now) == result
    current = await repository.state(db, user.id)
    for key in ("parameters", "parameters_version", "parameters_fingerprint", "optimized_at"):
        assert current[key] == previous[key]


async def test_511_transitions_never_invoke_optimizer(
    db: AsyncWsSurrealConnection, make_user: UserFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user()
    rows = history(user.id, cards=16, reviews=33)[:-1]

    async def get_history(*args: Any) -> list[dict[str, Any]]:
        return rows

    async def forbidden(*args: Any) -> tuple[str, object]:
        pytest.fail("Insufficient data must not invoke training")

    monkeypatch.setattr(repository, "history", get_history)
    monkeypatch.setattr(srs_optimization, "compute", forbidden)
    result = await srs_optimization.optimize(db, user.id)
    assert result.status == "insufficient_history" and result.eligible_reviews == 511


async def test_concurrent_claim_and_stale_finish_cannot_overwrite_newer_run(
    db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    user = await make_user()
    now = datetime.now(UTC)
    claims = await asyncio.gather(
        repository.claim(db, user.id, now), repository.claim(db, user.id, now)
    )
    assert sum(run is not None for run in claims) == 1
    first = next(run for run in claims if run is not None)
    second_at = now + timedelta(minutes=11)
    second = await repository.claim(db, user.id, second_at)
    assert second is not None and second != first
    newer = OptimizationRead(
        status="success", at=second_at, eligible_reviews=512, history_fingerprint="b" * 64
    )
    values = list(DEFAULT_PARAMETERS)
    values[0] = 1.0
    assert await repository.finish(db, user.id, second, newer, values)
    older = newer.model_copy(update={"history_fingerprint": "c" * 64})
    assert not await repository.finish(db, user.id, first, older, list(DEFAULT_PARAMETERS))
    row = await repository.state(db, user.id)
    assert row["parameters"] == values and row["parameters_fingerprint"] == "b" * 64


async def test_only_future_confirmation_uses_weights_and_retention(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    owner = study.user.id
    prefs = UserPreferences(theme="dark", locale="en", accent="UK", desired_retention=0.95)
    await set_preferences(db, owner, prefs)
    first_at = datetime.now(UTC) - timedelta(days=1)
    first_review = await graded(db, study)
    first = await srs.apply_review(db, owner, first_review, Rating.Good, now=first_at)
    before_cards = await owned(db, "memory", user_record(owner))
    before_logs = await owned(db, "review_log", user_record(owner))
    values = list(DEFAULT_PARAMETERS)
    values[8] = 4.0
    await store_parameters(db, owner, first_at + timedelta(hours=1), values)
    assert await owned(db, "memory", user_record(owner)) == before_cards
    assert await owned(db, "review_log", user_record(owner)) == before_logs
    assert await srs.apply_review(db, owner, first_review, Rating.Good, now=first_at) == first
    loaded = await find_user(db, owner)
    assert loaded is not None and loaded.prefs == prefs

    monkeypatch.setattr("fsrs.scheduler.random", lambda: 0.5)
    future_at = first_at + timedelta(days=2)
    next_review = await graded(db, study)
    expected, _ = Scheduler(parameters=values, desired_retention=0.95).review_card(
        first.memory.card.to_card(), Rating.Good, review_datetime=future_at
    )
    default, _ = Scheduler(desired_retention=0.95).review_card(
        first.memory.card.to_card(), Rating.Good, review_datetime=future_at
    )
    other_retention, _ = Scheduler(parameters=values, desired_retention=0.8).review_card(
        first.memory.card.to_card(), Rating.Good, review_datetime=future_at
    )
    result = await srs.apply_review(db, owner, next_review, Rating.Good, now=future_at)
    assert result.memory.card.stability == expected.stability != default.stability
    assert result.memory.card.due == expected.due != other_retention.due
    assert await srs.apply_review(db, owner, first_review, Rating.Good, now=first_at) == first
    logs, excluded = training_history(
        await repository.history(db, owner), owner, future_at + timedelta(seconds=1)
    )
    assert len(logs) == 2 and excluded == 0
    loaded = await find_user(db, owner)
    assert loaded is not None and loaded.prefs == prefs


@pytest.mark.parametrize("fault", ["absent", "invalid", "old_version"])
async def test_missing_invalid_or_foreign_weights_fall_back_to_defaults(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    fault: str,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    other = await create_study(db, make_user, lexicon_reader)
    now = datetime.now(UTC)
    values = list(DEFAULT_PARAMETERS)
    values[2] = 10.0
    await store_parameters(db, other.user.id, now, values)
    if fault != "absent":
        await store_parameters(db, study.user.id, now, values)
        await replace_parameters(
            db,
            study.user.id,
            [101.0] * 21 if fault == "invalid" else values,
            "old-version" if fault == "old_version" else OPTIMIZER_VERSION,
        )
    own = await srs.apply_review(db, study.user.id, await graded(db, study), Rating.Good, now=now)
    foreign = await srs.apply_review(
        db, other.user.id, await graded(db, other), Rating.Good, now=now
    )
    assert own.memory.card.stability == DEFAULT_PARAMETERS[2]
    assert foreign.memory.card.stability == values[2]
