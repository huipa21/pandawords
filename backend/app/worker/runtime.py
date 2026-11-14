import asyncio
from collections.abc import Coroutine
from contextlib import suppress
from typing import Any

import structlog
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.db.client import database_lifespan
from app.domain.jobs import Job
from app.services import jobs
from app.worker.handlers import HANDLERS, Handler
from app.worker.wakeup import POLL_SECONDS, LiveWakeup


async def _settle[T](operation: Coroutine[Any, Any, T]) -> T:
    task = asyncio.create_task(operation)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            with suppress(asyncio.CancelledError):
                await asyncio.shield(task)
        task.result()
        raise


async def execute(
    db: AsyncSurrealConnection, job: Job, handlers: dict[str, Handler] | None = None
) -> None:
    handler = (HANDLERS if handlers is None else handlers).get(job.type)
    if handler is None:
        await _settle(jobs.fail(db, job, terminal=True))
        return
    try:
        await handler(job)
    except asyncio.CancelledError:
        await _settle(jobs.fail(db, job, cancelled=True))
        raise
    except Exception as exc:
        structlog.get_logger().warning(
            "worker_handler_failed", job_id=job.id, error_type=type(exc).__name__
        )
        await _settle(jobs.fail(db, job))
    else:
        await _settle(jobs.complete(db, job))


async def run_once(db: AsyncSurrealConnection, handlers: dict[str, Handler] | None = None) -> bool:
    pending = asyncio.create_task(jobs.claim(db))
    try:
        job = await asyncio.shield(pending)
    except asyncio.CancelledError:
        while not pending.done():
            with suppress(asyncio.CancelledError):
                await asyncio.shield(pending)
        job = pending.result()
        if job is not None:
            await _settle(jobs.fail(db, job, cancelled=True))
        raise
    if job is None:
        return False
    await execute(db, job, handlers)
    return True


async def run_worker(settings: Settings) -> None:
    wakeup = asyncio.Event()
    live = asyncio.create_task(LiveWakeup(settings, wakeup).listen(), name="worker_live")
    try:
        async with database_lifespan(settings) as database:
            while True:
                wakeup.clear()
                try:
                    db = await database.get_connection()
                    if await run_once(db):
                        continue
                except Exception as exc:
                    structlog.get_logger().error(
                        "worker_iteration_failed", error_type=type(exc).__name__
                    )
                    # An outage must not spin, even if LIVE keeps generating hints.
                    await asyncio.sleep(POLL_SECONDS)
                    continue
                with suppress(TimeoutError):
                    await asyncio.wait_for(wakeup.wait(), timeout=POLL_SECONDS)
    finally:
        live.cancel()
        with suppress(asyncio.CancelledError):
            await live
