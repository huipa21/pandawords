"""Migration metadata and checked, transaction-bound query execution."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

TRACKING_SCHEMA = """
DEFINE TABLE IF NOT EXISTS _migration SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS version ON _migration TYPE string;
DEFINE FIELD IF NOT EXISTS name ON _migration TYPE string;
DEFINE FIELD IF NOT EXISTS checksum ON _migration TYPE string;
DEFINE FIELD IF NOT EXISTS applied_at ON _migration TYPE datetime;
DEFINE INDEX IF NOT EXISTS migration_version ON _migration FIELDS version UNIQUE;
"""


class MigrationError(Exception):
    """A migration could not be safely applied."""


async def checked_query(
    db: AsyncWsSurrealConnection,
    query: str,
    variables: dict[str, Value] | None = None,
    *,
    txn_id: UUID | None = None,
) -> list[Any]:
    response = await db.query_raw(query, variables, txn_id=txn_id)
    if "error" in response:
        raise MigrationError(f"Database query failed: {response['error']}")
    statements = response.get("result")
    if not isinstance(statements, list):
        raise MigrationError(f"Unexpected database response: {response!r}")
    results: list[Any] = []
    for statement in statements:
        if not isinstance(statement, dict) or statement.get("status") != "OK":
            raise MigrationError(f"Database statement failed: {statement!r}")
        results.append(statement.get("result"))
    return results


class MigrationConnection:
    """Only expose checked queries bound to the runner-owned UUID transaction."""

    def __init__(self, db: AsyncWsSurrealConnection, txn_id: UUID) -> None:
        self._db = db
        self._txn_id = txn_id
        self.failed = False

    async def query(self, query: str, variables: dict[str, Value] | None = None) -> list[Any]:
        try:
            return await checked_query(self._db, query, variables, txn_id=self._txn_id)
        except BaseException:
            self.failed = True
            raise


async def applied_migrations(db: AsyncWsSurrealConnection) -> list[dict[str, Any]]:
    info = (await checked_query(db, "INFO FOR DB;"))[0]
    if "_migration" not in info["tables"]:
        return []
    return (await checked_query(db, "SELECT * FROM _migration ORDER BY version;"))[0]
