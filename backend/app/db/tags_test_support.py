"""Synthetic tag graph fixtures, kept with the database-only query boundary."""

from typing import Any
from uuid import uuid4

from surrealdb import AsyncSurrealConnection, RecordID

from app.db.auth import _rows
from app.domain.identity import user_key
from app.domain.tags import TagTarget


async def target(
    db: AsyncSurrealConnection,
    table: TagTarget,
    owner: str | None = None,
) -> RecordID:
    record = RecordID(table, uuid4().hex)
    content = {
        "tag": {"name": "Shared source", "kind": "domain"},
        "sense": {
            "definition": "A test sense",
            "common": False,
            "rank": 0,
            "register": [],
            "domain": [],
            "examples": [],
            "gloss": {},
            "source": "custom",
        },
        "morpheme": {"text": "test", "type": "root"},
    }[table]
    await _rows(
        db,
        "CREATE $id CONTENT $content;",
        {
            "id": record,
            "content": {
                **content,
                "owner": RecordID("user", user_key(owner)) if owner else None,
            },
        },
    )
    return record


async def edge(
    db: AsyncSurrealConnection,
    source: RecordID,
    tag: RecordID,
    owner: str | None,
) -> RecordID:
    edge = RecordID("member_of", uuid4().hex)
    await _rows(
        db,
        "RELATE $source->$edge->$tag SET owner = $owner;",
        {
            "source": source,
            "edge": edge,
            "tag": tag,
            "owner": RecordID("user", user_key(owner)) if owner else None,
        },
    )
    return edge


async def edges(db: AsyncSurrealConnection, source: RecordID) -> list[dict[str, Any]]:
    return await _rows(
        db,
        "SELECT * FROM member_of WHERE in = $source OR out = $source;",
        {"source": source},
    )


async def remove_edge(db: AsyncSurrealConnection, edge: RecordID) -> None:
    await _rows(db, "DELETE $edge;", {"edge": edge})
