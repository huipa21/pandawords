"""Owner-bound probes for the memory schema's real-database tests."""

from typing import Any

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db.migration_store import checked_query


async def owned(db: AsyncWsSurrealConnection, table: str, owner: RecordID) -> list[dict[str, Any]]:
    return (
        await checked_query(
            db,
            "SELECT * FROM type::table($table) WHERE owner = $owner ORDER BY id;",
            {"table": table, "owner": owner},
        )
    )[0]
