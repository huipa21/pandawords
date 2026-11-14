import re
from datetime import UTC, datetime, timedelta

from surrealdb import AsyncSurrealConnection

from app.core.errors import AppError
from app.db import jobs as repository
from app.domain.jobs import Job, JobCreate, JobRead

MAX_ATTEMPTS = 5


async def enqueue(db: AsyncSurrealConnection, data: JobCreate) -> Job:
    return await repository.enqueue(db, data)


async def claim(db: AsyncSurrealConnection) -> Job | None:
    return await repository.claim(db)


async def read(db: AsyncSurrealConnection, key: str, owner: str) -> JobRead:
    # IDs are opaque, generated 32-character hex keys, never SurrealQL expressions.
    if not re.fullmatch(r"[0-9a-f]{32}", key):
        raise AppError("job.not_found", 404, "Job not found.")
    job = await repository.read(db, key, owner)
    if job is None:
        raise AppError("job.not_found", 404, "Job not found.")
    return JobRead.model_validate(job.model_dump(exclude={"owner", "payload"}))


def retry_delay(attempts: int) -> float:
    return float(2 ** min(max(attempts - 1, 0), 8))


async def complete(db: AsyncSurrealConnection, job: Job) -> None:
    await repository.finish(db, job, "done", datetime.now(UTC), None)


async def fail(
    db: AsyncSurrealConnection, job: Job, *, terminal: bool = False, cancelled: bool = False
) -> None:
    exhausted = terminal or job.attempts >= MAX_ATTEMPTS
    error = "unknown_handler" if terminal else "worker_cancelled" if cancelled else "handler_failed"
    await repository.finish(
        db,
        job,
        "failed" if exhausted else "queued",
        datetime.now(UTC) + timedelta(seconds=retry_delay(job.attempts)),
        error,
    )
