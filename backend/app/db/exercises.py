"""Owner-bound durable attempts; callers serialize mutations with the SDK transaction."""

from datetime import datetime
from typing import cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db.auth import _rows
from app.db.srs import user_record
from app.domain.exercises import Attempt


async def read(db: AsyncSurrealConnection, owner: str, attempt_id: str, txn: UUID) -> Attempt:
    if len(attempt_id) != 32 or any(char not in "0123456789abcdef" for char in attempt_id):
        raise AppError("exercise.not_found", 404, "Attempt not found.")
    rows = await _rows(
        db,
        "SELECT payload FROM $attempt WHERE owner = $user;",
        {"attempt": RecordID("exercise_attempt", attempt_id), "user": user_record(owner)},
        txn_id=txn,
    )
    if not rows:
        raise AppError("exercise.not_found", 404, "Attempt not found.")
    attempt = Attempt.model_validate_json(rows[0]["payload"])
    if attempt.owner != owner or attempt.id != attempt_id:
        raise AppError("exercise.not_found", 404, "Attempt not found.")
    return attempt


async def open_leases_after(
    db: AsyncSurrealConnection, owner: str, after: datetime, txn: UUID
) -> list[Attempt]:
    """Unconfirmed, unexpired offline attempts, including the last online-TTL minutes."""
    rows = await _rows(
        db,
        "SELECT payload, issued_at FROM exercise_attempt "
        "WHERE owner = $user AND status != 'confirmed' AND expires_at > $after ORDER BY issued_at, id;",
        {"user": user_record(owner), "after": after},
        txn_id=txn,
    )
    attempts = [Attempt.model_validate_json(row["payload"]) for row in rows]
    return [attempt for attempt in attempts if attempt.owner == owner and attempt.offline]


async def reserve_offline(
    db: AsyncSurrealConnection, attempt: Attempt, now: datetime, limit: int, txn: UUID
) -> Attempt | None:
    user = user_record(attempt.owner)
    await _rows(
        db,
        "UPSERT $id SET owner = $user, version += 1 "
        "WHERE owner = NONE OR owner = $user RETURN AFTER;",
        {"id": RecordID("offline_attempt_guard", [user]), "user": user},
        txn_id=txn,
    )
    held = await open_leases_after(db, attempt.owner, now, txn)
    for prior in held:
        if (
            prior.status == "open"
            and prior.project_id == attempt.project_id
            and prior.sense_id == attempt.sense_id
            and prior.expected_version == attempt.expected_version
        ):
            return prior
    if len(held) >= limit:
        raise AppError("exercise.offline_limit", 409, "Offline attempt limit reached.")
    return None


async def write(
    db: AsyncSurrealConnection, attempt: Attempt, txn: UUID, *, create: bool = False
) -> None:
    variables: dict[str, Value] = {
        "attempt": RecordID("exercise_attempt", attempt.id),
        "user": user_record(attempt.owner),
        "content": cast(
            Value,
            {
                "owner": user_record(attempt.owner),
                "project": decode_rid(attempt.project_id, "project"),
                "sense": decode_rid(attempt.sense_id, "sense"),
                "status": attempt.status,
                "issued_at": attempt.issued_at,
                "expires_at": attempt.expires_at,
                "payload": attempt.model_dump_json(),
            },
        ),
    }
    query = (
        "CREATE $attempt CONTENT $content;"
        if create
        else "UPDATE $attempt CONTENT $content WHERE owner = $user RETURN AFTER;"
    )
    rows = await _rows(db, query, variables, txn_id=txn)
    if not rows:
        raise AppError("exercise.not_found", 404, "Attempt not found.")
