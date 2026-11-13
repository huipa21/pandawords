"""Bound record writes for auth schema integration tests, not an auth service."""

from typing import Any

from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.migration_store import checked_query


async def create_user(db: AsyncWsSurrealConnection, attributes: dict[str, Value]) -> dict[str, Any]:
    return (
        await checked_query(db, "CREATE user CONTENT $attributes;", {"attributes": attributes})
    )[0][0]


async def create_refresh_token(
    db: AsyncWsSurrealConnection, attributes: dict[str, Value]
) -> dict[str, Any]:
    return (
        await checked_query(
            db, "CREATE refresh_token CONTENT $attributes;", {"attributes": attributes}
        )
    )[0][0]
