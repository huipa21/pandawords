from typing import Any, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.db.auth import _rows
from app.domain.identity import user_key, user_subject
from app.domain.media import Media, MediaCreate


def _owner(owner: str | None) -> RecordID | None:
    return RecordID("user", user_key(owner)) if owner is not None else None


async def target_visible(db: AsyncSurrealConnection, target: RecordID, owner: str | None) -> bool:
    rows = await db.query(
        "SELECT id FROM $target WHERE owner = NONE OR owner = $user;",
        {"target": target, "user": _owner(owner)},
    ).first()
    return isinstance(rows, list) and bool(rows)


async def create(
    db: AsyncSurrealConnection,
    record: RecordID,
    data: MediaCreate,
    path: str,
    *,
    txn_id: UUID | None = None,
) -> Media:
    content: dict[str, Value] = {
        "target": data.target,
        "owner": _owner(data.owner),
        "kind": data.kind,
        "mime": data.mime,
        "source": data.source,
        "path": path,
    }
    for key in ("attribution", "accent"):
        value = getattr(data, key)
        if value is not None:
            content[key] = value
    rows = await _rows(
        db, "CREATE $id CONTENT $data;", {"id": record, "data": content}, txn_id=txn_id
    )
    if not isinstance(rows, list) or not rows:
        raise ValueError("Invalid media query result")
    return _media(cast(dict[str, Any], rows[0]))


def _media(row: dict[str, Any]) -> Media:
    owner = row.get("owner")
    return Media.model_validate(
        {
            **row,
            "owner": user_subject(str(owner.id)) if isinstance(owner, RecordID) else None,
        }
    )


async def read(db: AsyncSurrealConnection, record: RecordID, owner: str) -> Media | None:
    rows = await db.query(
        "SELECT * FROM $id WHERE owner = NONE OR owner = $user;",
        {"id": record, "user": _owner(owner)},
    ).first()
    if not isinstance(rows, list) or not rows:
        return None
    return _media(cast(dict[str, Any], rows[0]))
