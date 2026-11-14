"""Bound-parameter dense fixtures for real graph query regression tests."""

from typing import cast
from uuid import uuid4

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.migration_store import checked_query


async def tags(
    db: AsyncWsSurrealConnection, user: RecordID, count: int, *, dense: bool = False
) -> list[RecordID]:
    records = [RecordID("tag", uuid4().hex) for _ in range(count)]
    await checked_query(
        db,
        "FOR $record IN $records { CREATE $record CONTENT "
        "{owner: $user, kind: 'custom', name: 'Bounded fixture'}; };",
        {"records": cast(Value, records), "user": user},
    )
    starts = records if dense else records[:1]
    for offset in range(0, len(starts), 5):
        await checked_query(
            db,
            "FOR $start IN $starts { FOR $target IN $targets { "
            "RELATE $start->member_of->$target CONTENT {owner: $user}; }; };",
            {
                "starts": cast(Value, starts[offset : offset + 5]),
                "targets": cast(Value, records if dense else records[1:]),
                "user": user,
            },
        )
    return records
