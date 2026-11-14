"""Bound probes for the dictionary migration integration tests."""

from typing import Any
from uuid import uuid4

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.migration_store import checked_query


async def table_info(db: AsyncWsSurrealConnection, table: str) -> dict[str, Any]:
    return (await checked_query(db, "INFO FOR TABLE $table;", {"table": table}))[0]


async def create(
    db: AsyncWsSurrealConnection, record: RecordID, attributes: dict[str, Value]
) -> dict[str, Any]:
    return (
        await checked_query(
            db, "CREATE $record CONTENT $attributes;", {"record": record, "attributes": attributes}
        )
    )[0][0]


async def relate(
    db: AsyncWsSurrealConnection,
    edge: str,
    start: RecordID,
    end: RecordID,
    attributes: dict[str, Value],
) -> dict[str, Any]:
    return (
        await checked_query(
            db,
            "RELATE $start->$edge->$end CONTENT $attributes;",
            {
                "start": start,
                "edge": RecordID(edge, uuid4().hex),
                "end": end,
                "attributes": attributes,
            },
        )
    )[0][0]


async def visible(db: AsyncWsSurrealConnection, table: str, user: RecordID) -> list[dict[str, Any]]:
    return (
        await checked_query(
            db,
            "SELECT * FROM type::table($table) WHERE owner = NONE OR owner = $user;",
            {"table": table, "user": user},
        )
    )[0]
