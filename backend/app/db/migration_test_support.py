"""Synthetic migration probes; all test SurrealQL stays in the database layer."""

from __future__ import annotations

from typing import Any

from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db.migration_store import checked_query

SUCCESS = """
DEFINE TABLE IF NOT EXISTS migration_probe SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS value ON migration_probe TYPE string;
CREATE migration_probe:row SET value = 'written';
"""
FAILURE = SUCCESS + "\nTHROW 'intentional_migration_failure';"
PYTHON_SUCCESS = f"""
from app.db.migration_store import MigrationConnection

async def up(db: MigrationConnection) -> None:
    await db.query({SUCCESS!r})
    await db.query("UPDATE migration_probe:row SET value = $value;", {{"value": "python"}})
"""
PYTHON_RAISE = PYTHON_SUCCESS + '\n    raise RuntimeError("intentional_python_failure")\n'
PYTHON_QUERY_FAILURE = PYTHON_SUCCESS + "\n    await db.query(\"THROW 'python_query_failure';\")\n"
PYTHON_SWALLOW = (
    PYTHON_SUCCESS
    + """
    try:
        await db.query("THROW 'swallowed_query_failure';")
    except Exception:
        pass
"""
)


async def history(db: AsyncWsSurrealConnection) -> list[dict[str, Any]]:
    return (await checked_query(db, "SELECT * FROM _migration ORDER BY version;"))[0]


async def tables(db: AsyncWsSurrealConnection) -> dict[str, str]:
    return (await checked_query(db, "INFO FOR DB;"))[0]["tables"]


async def probe_value(db: AsyncWsSurrealConnection) -> str:
    return (await checked_query(db, "SELECT VALUE value FROM migration_probe:row;"))[0][0]


async def invalidate_history_checksum(db: AsyncWsSurrealConnection) -> None:
    await checked_query(
        db, "UPDATE _migration SET checksum = $checksum;", {"checksum": "invalid-checksum"}
    )


async def remove_database(db: AsyncWsSurrealConnection, name: str) -> None:
    await checked_query(db, "REMOVE DATABASE IF EXISTS $database;", {"database": name})
    info = (await checked_query(db, "INFO FOR NS;"))[0]
    assert name not in info["databases"]
