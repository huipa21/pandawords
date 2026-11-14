import asyncio
from unittest.mock import patch

import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.jobs import live_queued
from app.db.jobs_test_support import worker_read
from app.domain.jobs import Job, JobCreate
from app.services import jobs
from app.worker.handlers import HANDLERS
from app.worker.runtime import run_worker
from app.worker.wakeup import LiveWakeup

pytestmark = pytest.mark.integration


async def cancel(task: asyncio.Task[None]) -> None:
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)


async def test_live_create_and_update_and_clean_kill(job_db: AsyncWsSurrealConnection) -> None:
    live_id = await live_queued(job_db)
    notifications = await job_db.subscribe_live(live_id)
    try:
        incoming = asyncio.create_task(anext(notifications))
        job = await jobs.enqueue(job_db, JobCreate(type="noop"))
        notice = await asyncio.wait_for(incoming, timeout=3)
        assert notice["action"] == "CREATE"
        result = notice["result"]
        assert isinstance(result, dict)
        record = result["id"]
        assert isinstance(record, RecordID)
        assert str(record.id) == job.id
        claimed = await jobs.claim(job_db)
        assert claimed is not None
        incoming = asyncio.create_task(anext(notifications))
        await jobs.fail(job_db, claimed)
        notice = await asyncio.wait_for(incoming, timeout=3)
        assert notice["action"] == "UPDATE"
    finally:
        await job_db.kill(live_id)
        await notifications.aclose()
    with pytest.raises(StopAsyncIteration):
        await anext(notifications)


async def test_live_disconnect_reconnects_new_subscription(
    job_db: AsyncWsSurrealConnection, job_settings: Settings
) -> None:
    wakeup = asyncio.Event()
    listener = LiveWakeup(job_settings, wakeup)
    task = asyncio.create_task(listener.listen())
    try:
        await asyncio.wait_for(listener.subscribed.wait(), timeout=3)
        old = listener.connection
        assert old is not None and old.socket is not None
        wakeup.clear()
        await jobs.enqueue(job_db, JobCreate(type="noop"))
        await asyncio.wait_for(wakeup.wait(), timeout=3)
        await old.socket.close()
        for _ in range(400):
            if listener.connection is not old and listener.subscribed.is_set():
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("LIVE did not reconnect within eight seconds")
        assert listener.connection is not old
        wakeup.clear()
        await jobs.enqueue(job_db, JobCreate(type="noop"))
        await asyncio.wait_for(wakeup.wait(), timeout=3)
    finally:
        await cancel(task)
    assert listener.connection is None
    assert not listener.subscribed.is_set()


async def test_poll_fallback_processes_jobs_when_live_is_unavailable(
    job_db: AsyncWsSurrealConnection, job_settings: Settings
) -> None:
    tasks_before = set(asyncio.all_tasks())
    failed = asyncio.Event()

    async def unavailable(_db: AsyncWsSurrealConnection) -> str:
        failed.set()
        raise ConnectionError("private-credential")

    with patch("app.worker.wakeup.live_queued", unavailable):
        task = asyncio.create_task(run_worker(job_settings))
        try:
            await asyncio.wait_for(failed.wait(), timeout=3)
            # Let the initial scan drain; this subsequent job must be found by polling.
            await asyncio.sleep(0.1)
            job = await jobs.enqueue(job_db, JobCreate(type="noop"))
            for _ in range(140):
                if (await worker_read(job_db, job)).status == "done":
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("Polling did not complete the queued job within seven seconds")
            assert (await worker_read(job_db, job)).attempts == 1
        finally:
            await cancel(task)
    await asyncio.sleep(0)
    assert not [t for t in asyncio.all_tasks() - tasks_before if not t.done()]


async def test_worker_shutdown_cancels_handler_live_and_database_tasks(
    job_db: AsyncWsSurrealConnection, job_settings: Settings
) -> None:
    job = await jobs.enqueue(job_db, JobCreate(type="waiting"))
    started = asyncio.Event()
    released = asyncio.Event()
    tasks_before = set(asyncio.all_tasks())

    async def waiting(_job: Job) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            released.set()

    with patch.dict(HANDLERS, {"waiting": waiting}):
        task = asyncio.create_task(run_worker(job_settings))
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
        finally:
            await cancel(task)
    assert released.is_set()
    stored = await worker_read(job_db, job)
    assert (stored.status, stored.error) == ("queued", "worker_cancelled")
    await asyncio.sleep(0)
    assert not [t for t in asyncio.all_tasks() - tasks_before if not t.done()]
