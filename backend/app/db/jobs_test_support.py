"""Bound updates used only to advance the clock in job retry regressions."""

from datetime import UTC, datetime

from surrealdb import AsyncSurrealConnection, RecordID

from app.domain.identity import user_key
from app.domain.jobs import Job


async def make_due(db: AsyncSurrealConnection, job: Job) -> None:
    await db.query(
        "UPDATE $id SET run_after = $now WHERE owner = $owner;",
        {
            "id": RecordID("job", job.id),
            "now": datetime.now(UTC),
            "owner": RecordID("user", user_key(job.owner)) if job.owner else None,
        },
    )


async def worker_read(db: AsyncSurrealConnection, job: Job) -> Job:
    from app.db.jobs import _job, _rows

    rows = await _rows(
        db,
        "SELECT * FROM $id WHERE owner = $owner;",
        {
            "id": RecordID("job", job.id),
            "owner": RecordID("user", user_key(job.owner)) if job.owner else None,
        },
    )
    return _job(rows[0])


async def mark_running(db: AsyncSurrealConnection, job: Job) -> None:
    await db.query(
        "UPDATE $id SET status = 'running' WHERE owner = $owner;",
        {
            "id": RecordID("job", job.id),
            "owner": RecordID("user", user_key(job.owner)) if job.owner else None,
        },
    )
