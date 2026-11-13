"""Canonical schema metadata, including every table's fields, indexes and events."""

from __future__ import annotations

import json
from pathlib import Path

from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db.migration_store import checked_query

SNAPSHOT = Path(__file__).with_name("schema.snapshot.json")


async def snapshot(db: AsyncWsSurrealConnection) -> str:
    database = (await checked_query(db, "INFO FOR DB;"))[0]
    tables = {}
    for table in sorted(database["tables"]):
        tables[table] = (await checked_query(db, "INFO FOR TABLE $table;", {"table": table}))[0]
    # Keep definition strings intact: whitespace inside literals can be significant.
    return json.dumps({"database": database, "tables": tables}, sort_keys=True, indent=2) + "\n"
