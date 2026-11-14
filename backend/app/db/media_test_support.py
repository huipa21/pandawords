"""Synthetic media targets and corruption probes, used only by tests."""

from collections.abc import Mapping
from uuid import uuid4

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.domain.identity import user_key


async def target(db: AsyncSurrealConnection, owner: str | None = None) -> RecordID:
    record = RecordID("tag", uuid4().hex)
    await db.query(
        "CREATE $id SET name = 'media test', kind = 'custom', owner = $owner;",
        {"id": record, "owner": RecordID("user", user_key(owner)) if owner else None},
    )
    return record


async def change(db: AsyncSurrealConnection, record: RecordID, data: Mapping[str, Value]) -> None:
    await db.query("UPDATE $id MERGE $data;", {"id": record, "data": dict(data)})


async def remove(db: AsyncSurrealConnection, record: RecordID) -> None:
    await db.query("DELETE $id;", {"id": record})
