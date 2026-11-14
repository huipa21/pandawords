"""Transactional attempt/history probes for real database acceptance tests."""

from uuid import UUID

from surrealdb import AsyncSurrealConnection

from app.core.record_ids import decode_rid
from app.db import exercises
from app.db.auth import _atomic, _rows
from app.db.srs import user_record
from app.domain.exercises import Attempt


async def saved(db: AsyncSurrealConnection, owner: str, attempt_id: str) -> Attempt:
    async def operation(txn: UUID) -> Attempt:
        return await exercises.read(db, owner, attempt_id, txn)

    return await _atomic(db, operation)


async def logs(db: AsyncSurrealConnection, owner: str) -> list[dict]:
    return await _rows(
        db,
        "SELECT * FROM review_log WHERE owner = $user;",
        {"user": user_record(owner)},
    )


async def remove_membership(
    db: AsyncSurrealConnection, owner: str, project_id: str, sense_id: str
) -> None:
    await _rows(
        db,
        "DELETE includes WHERE owner = $user AND in = $project AND out = $sense;",
        {
            "user": user_record(owner),
            "project": decode_rid(project_id, "project"),
            "sense": decode_rid(sense_id, "sense"),
        },
    )
