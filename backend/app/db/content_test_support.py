"""Synthetic association probes for content isolation and rollback tests."""

from uuid import uuid4

from surrealdb import AsyncSurrealConnection, RecordID

from app.db.auth import _rows
from app.db.content import actor


async def counts(db: AsyncSurrealConnection, owner: str) -> dict[str, int]:
    result = {}
    for table in ("sentence", "passage", "used_in", "part_of"):
        rows = await _rows(
            db,
            "SELECT id FROM type::table($table) WHERE owner = $user;",
            {"table": table, "user": actor(owner)},
        )
        result[table] = len(rows)
    return result


async def foreign_part(
    db: AsyncSurrealConnection, owner: str, sentence: RecordID, passage: RecordID
) -> RecordID:
    edge = RecordID("part_of", uuid4().hex)
    await _rows(
        db,
        "RELATE $sentence->$edge->$passage CONTENT $fields;",
        {
            "sentence": sentence,
            "edge": edge,
            "passage": passage,
            "fields": {"owner": actor(owner), "order": 99},
        },
    )
    return edge


async def foreign_link(
    db: AsyncSurrealConnection, owner: str, sentence: RecordID, sense: RecordID
) -> RecordID:
    edge = RecordID("used_in", uuid4().hex)
    await _rows(
        db,
        "RELATE $sense->$edge->$sentence CONTENT $fields;",
        {
            "sentence": sentence,
            "edge": edge,
            "sense": sense,
            "fields": {"owner": actor(owner), "span": [0, 3]},
        },
    )
    return edge


async def private_sense(db: AsyncSurrealConnection, owner: str) -> RecordID:
    record = RecordID("sense", uuid4().hex)
    await _rows(
        db,
        "CREATE $record CONTENT $fields;",
        {
            "record": record,
            "fields": {
                "owner": actor(owner),
                "definition": "Private test sense",
                "gloss": {},
                "register": [],
                "domain": [],
                "examples": [],
                "rank": 1,
                "common": False,
                "source": "user",
            },
        },
    )
    return record


async def shared_counts(db: AsyncSurrealConnection) -> dict[str, int]:
    result = {}
    for table in ("lemma", "lexeme", "sense", "has_lexeme", "has_sense"):
        rows = await _rows(
            db, "SELECT id FROM type::table($table) WHERE owner = NONE;", {"table": table}
        )
        result[table] = len(rows)
    return result
