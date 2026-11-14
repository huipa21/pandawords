"""Job persistence; worker-only scans deliberately cover every owner."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.errors import QueryDetailKind, ServerError

from app.db.auth import _atomic, _rows
from app.domain.identity import user_key, user_subject
from app.domain.jobs import Job, JobCreate, JobStatus


def _job(row: dict[str, Any]) -> Job:
    record = row["id"]
    owner = row.get("owner")
    if not isinstance(record, RecordID) or record.table_name != "job":
        raise ValueError("Invalid job record")
    return Job.model_validate(
        {
            **row,
            "id": str(record.id),
            "owner": user_subject(str(owner.id)) if isinstance(owner, RecordID) else None,
        }
    )


async def enqueue(
    db: AsyncSurrealConnection,
    data: JobCreate,
    *,
    dedup_key: str | None = None,
    txn_id: UUID | None = None,
) -> Job:
    if dedup_key is not None and txn_id is None:

        async def operation(txn: UUID) -> Job:
            return await enqueue(db, data, dedup_key=dedup_key, txn_id=txn)

        return await _atomic(db, operation)
    owner = RecordID("user", user_key(data.owner)) if data.owner else None
    key = (
        uuid4().hex
        if dedup_key is None
        else hashlib.sha256(
            json.dumps([data.owner, data.type, dedup_key], separators=(",", ":")).encode()
        ).hexdigest()[:32]
    )
    record = RecordID("job", key)
    if dedup_key is not None:
        existing = await _rows(
            db,
            "SELECT * FROM $id WHERE owner = $owner;",
            {"id": record, "owner": owner},
            txn_id=txn_id,
        )
        if existing:
            return _job(existing[0])
    rows = await _rows(
        db,
        "CREATE $id CONTENT $data;",
        {
            "id": record,
            "data": {
                "type": data.type,
                "payload": data.payload,
                "owner": owner,
                "status": "queued",
                "attempts": 0,
                "run_after": data.run_after or datetime.now(UTC),
            },
        },
        txn_id=txn_id,
    )
    return _job(rows[0])


async def read(db: AsyncSurrealConnection, key: str, owner: str) -> Job | None:
    rows = await _rows(
        db,
        "SELECT * FROM $id WHERE owner = $user;",
        {"id": RecordID("job", key), "user": RecordID("user", user_key(owner))},
    )
    return _job(rows[0]) if rows else None


async def claim(db: AsyncSurrealConnection) -> Job | None:
    # SELECT is only a hint. The conditional UPDATE is the sole claim authority.
    for attempt in range(5):
        try:
            rows = await _rows(
                db,
                "SELECT * FROM job WHERE status = 'queued' AND run_after <= time::now() "
                "ORDER BY run_after LIMIT 1;",
                {},
            )
            if not rows:
                return None
            rows = await _rows(
                db,
                "UPDATE $id SET status = 'running', attempts += 1, error = NONE "
                "WHERE status = 'queued' AND attempts = $attempts "
                "AND run_after <= time::now() RETURN AFTER;",
                {"id": rows[0]["id"], "attempts": rows[0]["attempts"]},
            )
            if rows:
                return _job(rows[0])
        except ServerError as exc:
            if not (
                exc.details
                and exc.details.get("kind") == QueryDetailKind.TRANSACTION_CONFLICT
                and attempt < 4
            ):
                raise
        await asyncio.sleep(0.01 * (attempt + 1))
    return None


async def finish(
    db: AsyncSurrealConnection,
    job: Job,
    status: JobStatus,
    run_after: datetime,
    error: str | None,
) -> None:
    rows = await _rows(
        db,
        "UPDATE $id SET status = $status, run_after = $run_after, error = $error "
        "WHERE status = 'running' AND attempts = $attempts AND owner = $owner RETURN AFTER;",
        {
            "id": RecordID("job", job.id),
            "status": status,
            "attempts": job.attempts,
            "run_after": run_after,
            "error": error,
            "owner": RecordID("user", user_key(job.owner)) if job.owner else None,
        },
    )
    if len(rows) != 1:
        raise RuntimeError("Job completion lost its claim")


async def live_queued(db: AsyncSurrealConnection) -> str:
    result = await db.query("LIVE SELECT * FROM job WHERE status = 'queued';").first()
    return str(result)
