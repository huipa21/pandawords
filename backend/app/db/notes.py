from typing import Any, Literal
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.db.user_dictionary import require_visible
from app.domain.identity import user_key
from app.domain.notes import NoteCreate, NoteRead, NoteUpdate


def _read(row: dict[str, Any]) -> NoteRead:
    target = row["target"]
    return NoteRead(
        id=encode_rid(row["id"], "note"),
        target_table=target.table_name,
        target_id=encode_rid(target, target.table_name),
        kind=row["kind"],
        text=row["text"],
    )


async def create(
    db: AsyncSurrealConnection, owner: str, target: RecordID, data: NoteCreate
) -> NoteRead:
    async def operation(txn: UUID) -> NoteRead:
        user = RecordID("user", user_key(owner))
        await require_visible(db, user, target, txn)
        rows = await _rows(
            db,
            "CREATE $note CONTENT $content RETURN AFTER;",
            {
                "note": RecordID("note", uuid4().hex),
                "content": {"owner": user, "target": target, "kind": data.kind, "text": data.text},
            },
            txn_id=txn,
        )
        return _read(rows[0])

    return await _atomic(db, operation)


async def list_notes(db: AsyncSurrealConnection, owner: str, target: RecordID) -> list[NoteRead]:
    async def operation(txn: UUID) -> list[NoteRead]:
        user = RecordID("user", user_key(owner))
        await require_visible(db, user, target, txn)
        rows = await _rows(
            db,
            "SELECT * FROM note WHERE owner = $user AND target = $target ORDER BY id;",
            {"user": user, "target": target},
            txn_id=txn,
        )
        return [_read(row) for row in rows]

    return await _atomic(db, operation)


async def manage(
    db: AsyncSurrealConnection,
    owner: str,
    note: RecordID,
    *,
    action: Literal["get", "patch", "delete"],
    data: NoteUpdate | None = None,
) -> NoteRead | None:
    async def operation(txn: UUID) -> NoteRead | None:
        user = RecordID("user", user_key(owner))
        params: dict[str, Value] = {"note": note, "user": user}
        rows = await _rows(db, "SELECT * FROM $note WHERE owner = $user;", params, txn_id=txn)
        if not rows:
            raise AppError("note.not_found", 404, "Note not found.")
        await require_visible(db, user, rows[0]["target"], txn)
        if action == "delete":
            await _rows(db, "DELETE $note WHERE owner = $user RETURN BEFORE;", params, txn_id=txn)
            return None
        if data is not None:
            rows = await _rows(
                db,
                "UPDATE $note MERGE $changes WHERE owner = $user RETURN AFTER;",
                {**params, "changes": data.model_dump(exclude_unset=True)},
                txn_id=txn,
            )
        return _read(rows[0])

    return await _atomic(db, operation)
