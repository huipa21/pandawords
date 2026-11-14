"""Owner-bound probes for project and overlay schema integration tests."""

from typing import Any

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.migration_store import checked_query


async def owned(db: AsyncWsSurrealConnection, table: str, user: RecordID) -> list[dict[str, Any]]:
    return (
        await checked_query(
            db,
            "SELECT * FROM type::table($table) WHERE owner = $user;",
            {"table": table, "user": user},
        )
    )[0]


async def set_hidden(
    db: AsyncWsSurrealConnection, edge: RecordID, user: RecordID, hidden: bool
) -> list[dict[str, Any]]:
    return (
        await checked_query(
            db,
            "UPDATE $edge SET hidden = $hidden WHERE owner = $user RETURN AFTER;",
            {"edge": edge, "user": user, "hidden": hidden},
        )
    )[0]


async def visible_items(
    db: AsyncWsSurrealConnection, project: RecordID, user: RecordID
) -> list[dict[str, Any]]:
    return (
        await checked_query(
            db,
            "SELECT * FROM includes WHERE in = $project AND owner = $user "
            "AND in.owner = $user AND hidden = false "
            "AND (out.owner = NONE OR out.owner = $user);",
            {"project": project, "user": user},
        )
    )[0]


async def put_override(
    db: AsyncWsSurrealConnection, user: RecordID, target: RecordID, fields: dict[str, Value]
) -> dict[str, Any]:
    return (
        await checked_query(
            db,
            "UPSERT $overlay SET owner = $user, fields = $fields, updated_at = time::now() "
            "WHERE owner = NONE OR owner = $user RETURN AFTER;",
            {"overlay": RecordID("override", [user, target]), "user": user, "fields": fields},
        )
    )[0][0]


async def reset_override(db: AsyncWsSurrealConnection, user: RecordID, target: RecordID) -> None:
    await checked_query(
        db,
        "DELETE $overlay WHERE owner = $user;",
        {"overlay": RecordID("override", [user, target]), "user": user},
    )
