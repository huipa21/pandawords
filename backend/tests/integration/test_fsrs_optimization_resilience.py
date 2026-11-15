import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fsrs.scheduler import DEFAULT_PARAMETERS
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db import srs_optimization as repository
from app.db.srs_optimization_test_support import replace_parameters
from app.domain.srs_optimization import OPTIMIZER_VERSION, OptimizationRead
from app.services import srs_optimization
from tests.conftest import UserFactory
from tests.srs_optimization_support import history

pytestmark = pytest.mark.integration


async def store_previous(db: AsyncWsSurrealConnection, owner: str, now: datetime) -> list[float]:
    values = list(DEFAULT_PARAMETERS)
    values[0] = 1.0
    run = await repository.claim(db, owner, now)
    assert run is not None
    result = OptimizationRead(
        status="success", at=now, eligible_reviews=512, history_fingerprint="a" * 64
    )
    assert await repository.finish(db, owner, run, result, values)
    return values


async def test_cancellation_records_failure_and_keeps_last_good_parameters(
    db: AsyncWsSurrealConnection, make_user: UserFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user()
    now = datetime.now(UTC)
    values = await store_previous(db, user.id, now - timedelta(days=31))
    rows = history(
        user.id, cards=16, reviews=33, start=now - timedelta(days=35), interval=timedelta(days=1)
    )
    started = asyncio.Event()

    async def get_history(*args: Any) -> list[dict[str, Any]]:
        return rows

    async def compute(*args: Any) -> tuple[str, object]:
        started.set()
        await asyncio.Event().wait()
        return "failed", None

    monkeypatch.setattr(repository, "history", get_history)
    monkeypatch.setattr(srs_optimization, "compute", compute)
    task = asyncio.create_task(srs_optimization.optimize(db, user.id, now=now))
    await asyncio.wait_for(started.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = await srs_optimization.read(db, user.id)
    assert (result.status, result.reason) == ("failed", "cancelled")
    assert (await repository.state(db, user.id))["parameters"] == values


async def test_optimizer_version_change_can_retrain_without_new_history(
    db: AsyncWsSurrealConnection, make_user: UserFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user()
    now = datetime.now(UTC)
    values = await store_previous(db, user.id, now)
    await replace_parameters(db, user.id, values, "older-version")
    rows = history(user.id, cards=16, reviews=33)
    values[0] = 2.0

    async def get_history(*args: Any) -> list[dict[str, Any]]:
        return rows

    async def compute(*args: Any) -> tuple[str, object]:
        return "success", values

    monkeypatch.setattr(repository, "history", get_history)
    monkeypatch.setattr(srs_optimization, "compute", compute)
    result = await srs_optimization.optimize(db, user.id, now=now + timedelta(minutes=1))
    assert result.status == "success"
    state = await repository.state(db, user.id)
    assert state["parameters"] == values and state["parameters_version"] == OPTIMIZER_VERSION
