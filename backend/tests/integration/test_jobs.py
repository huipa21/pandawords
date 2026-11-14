import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from surrealdb import AsyncSurrealConnection
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.config import Settings
from app.db import jobs as repository
from app.db.jobs_test_support import make_due, worker_read
from app.domain.jobs import Job, JobCreate
from app.services import jobs
from app.worker.runtime import execute, run_once

pytestmark = pytest.mark.integration


async def test_independent_workers_conditional_claim_once(
    job_db: AsyncWsSurrealConnection, job_settings: Settings
) -> None:
    assert await job_db.version() == "surrealdb-3.3.5"
    job = await jobs.enqueue(job_db, JobCreate(type="race"))
    calls: list[str] = []
    candidates: list[str] = []
    selected = asyncio.Event()
    count = 0
    original = repository._rows

    async def synchronized(
        db: AsyncSurrealConnection, query: str, params: dict[str, Value]
    ) -> list[dict[str, Any]]:
        nonlocal count
        rows = await original(db, query, params)
        if query.startswith("SELECT * FROM job") and rows:
            candidates.append(str(rows[0]["id"].id))
            count += 1
            if count == 2:
                selected.set()
            await selected.wait()
        return rows

    async def handler(claimed: Job) -> None:
        calls.append(claimed.id)
        await asyncio.sleep(0.05)

    async with AsyncWsSurrealConnection(job_settings.surreal_url) as other:
        await other.signin(
            {"username": job_settings.surreal_user, "password": job_settings.surreal_pass}
        )
        await other.use(job_settings.surreal_namespace, job_settings.surreal_database)
        with patch.object(repository, "_rows", synchronized):
            results = await asyncio.wait_for(
                asyncio.gather(
                    run_once(job_db, {"race": handler}), run_once(other, {"race": handler})
                ),
                timeout=5,
            )
    assert sorted(results) == [False, True]
    assert candidates[:2] == [job.id, job.id]
    assert calls == [job.id]
    stored = await worker_read(job_db, job)
    assert stored.status == "done"
    assert stored.attempts == 1


async def test_failed_retries_are_scheduled_bounded_and_redacted(
    job_db: AsyncWsSurrealConnection,
) -> None:
    job = await jobs.enqueue(job_db, JobCreate(type="failing", payload={"secret": "credential"}))

    async def failing(_job: Job) -> None:
        raise RuntimeError("credential: never store exception messages")

    for attempt in range(1, jobs.MAX_ATTEMPTS + 1):
        before = datetime.now(UTC)
        assert await run_once(job_db, {"failing": failing})
        after = datetime.now(UTC)
        stored = await worker_read(job_db, job)
        assert stored.attempts == attempt
        assert stored.error == "handler_failed"
        assert before + timedelta(seconds=2 ** (attempt - 1)) <= stored.run_after
        assert stored.run_after <= after + timedelta(seconds=2 ** (attempt - 1))
        assert stored.status == ("failed" if attempt == jobs.MAX_ATTEMPTS else "queued")
        assert not await run_once(job_db, {"failing": failing})
        await make_due(job_db, job)
    assert not await run_once(job_db, {"failing": failing})


async def test_unknown_handler_terminal_and_noop_success(job_db: AsyncWsSurrealConnection) -> None:
    unknown = await jobs.enqueue(job_db, JobCreate(type="unregistered"))
    assert await run_once(job_db)
    stored = await worker_read(job_db, unknown)
    assert (stored.status, stored.attempts, stored.error) == ("failed", 1, "unknown_handler")
    assert not await run_once(job_db)
    noop = await jobs.enqueue(job_db, JobCreate(type="noop", payload={"nested": {"value": 1}}))
    assert await run_once(job_db)
    stored = await worker_read(job_db, noop)
    assert stored.status == "done"
    assert stored.payload == {"nested": {"value": 1}}


async def test_handler_cancellation_releases_claim(job_db: AsyncWsSurrealConnection) -> None:
    job = await jobs.enqueue(job_db, JobCreate(type="waiting"))
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def waiting(_job: Job) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(run_once(job_db, {"waiting": waiting}))
    await asyncio.wait_for(entered.wait(), timeout=3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    stored = await worker_read(job_db, job)
    assert (stored.status, stored.attempts, stored.error) == ("queued", 1, "worker_cancelled")
    assert not await run_once(job_db)


async def test_cancellation_during_claim_does_not_strand_job(
    job_db: AsyncWsSurrealConnection,
) -> None:
    job = await jobs.enqueue(job_db, JobCreate(type="noop"))
    committed = asyncio.Event()
    release = asyncio.Event()
    original = jobs.claim

    async def delayed(db: AsyncSurrealConnection) -> Job | None:
        claimed = await original(db)
        committed.set()
        await release.wait()
        return claimed

    with patch.object(jobs, "claim", delayed):
        task = asyncio.create_task(run_once(job_db))
        await asyncio.wait_for(committed.wait(), timeout=3)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    stored = await worker_read(job_db, job)
    assert stored.status == "queued"
    assert stored.error == "worker_cancelled"


async def test_cancel_at_retry_limit_is_terminal(job_db: AsyncWsSurrealConnection) -> None:
    job = await jobs.enqueue(job_db, JobCreate(type="noop"))
    for _ in range(jobs.MAX_ATTEMPTS - 1):
        claimed = await jobs.claim(job_db)
        assert claimed is not None
        await jobs.fail(job_db, claimed)
        await make_due(job_db, job)
    claimed = await jobs.claim(job_db)
    assert claimed is not None

    async def cancelling(_job: Job) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await execute(job_db, claimed, {"noop": cancelling})
    assert (await worker_read(job_db, job)).status == "failed"
