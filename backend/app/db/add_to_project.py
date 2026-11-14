"""Owner-validated atomic add boundary and deterministic project memberships."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.domain.identity import user_key


async def atomic_add[T](
    db: AsyncSurrealConnection,
    owner: str,
    project: RecordID,
    operation: Callable[[UUID], Awaitable[T]],
) -> T:
    async def authorized(txn: UUID) -> T:
        rows = await _rows(
            db,
            "SELECT id FROM $project WHERE owner = $user;",
            {"project": project, "user": RecordID("user", user_key(owner))},
            txn_id=txn,
        )
        if not rows:
            raise AppError("project.not_found", 404, "Project not found.")
        return await operation(txn)

    return await _atomic(db, authorized)


async def include(
    db: AsyncSurrealConnection,
    owner: str,
    project: RecordID,
    targets: list[RecordID],
    *,
    txn_id: UUID,
) -> list[str]:
    user = RecordID("user", user_key(owner))
    memberships: list[str] = []
    for target in targets:
        parameters: dict[str, Value] = {"project": project, "user": user, "target": target}
        existing = await _rows(
            db,
            "SELECT * FROM includes WHERE in = $project AND owner = $user "
            "AND in.owner = $user AND out = $target;",
            parameters,
            txn_id=txn_id,
        )
        if existing:
            # Also restore legacy memberships, retaining their IDs and original timestamps.
            rows = await _rows(
                db,
                "UPDATE includes SET hidden = false WHERE in = $project AND owner = $user "
                "AND in.owner = $user AND out = $target RETURN AFTER;",
                parameters,
                txn_id=txn_id,
            )
        else:
            rows = await _rows(
                db,
                "RELATE $project->$edge->$target CONTENT $content;",
                {
                    **parameters,
                    "edge": RecordID("includes", [project, target]),
                    "content": {"owner": user, "hidden": False, "added_at": datetime.now(UTC)},
                },
                txn_id=txn_id,
            )
        memberships.extend(encode_rid(row["id"], "includes") for row in rows)
    return memberships
