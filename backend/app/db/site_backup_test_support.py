"""Test-only reads for comparing a restored site database with its source."""

from __future__ import annotations

from typing import Any

from surrealdb import Table
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db.migration_store import checked_query


async def table_rows(db: AsyncWsSurrealConnection, table: str) -> list[Any]:
    return (await checked_query(db, "SELECT * FROM $table ORDER BY id;", {"table": Table(table)}))[
        0
    ]
