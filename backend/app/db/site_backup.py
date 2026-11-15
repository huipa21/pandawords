"""SurrealDB access for whole-site backup and restore (export/import over the SDK)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from surrealdb import Table
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.migration_store import MigrationError, checked_query

_EXPORT_HEADER_BYTES = 4096


@asynccontextmanager
async def connect(settings: Settings) -> AsyncIterator[AsyncWsSurrealConnection]:
    """Dedicated connection: the request connection's short timeout would cut off exports."""
    async with AsyncWsSurrealConnection(
        settings.surreal_url, timeout=settings.site_backup_timeout_seconds
    ) as db:
        await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
        await db.use(settings.surreal_namespace, settings.surreal_database)
        yield db


def _has_import_header(path: Path) -> bool:
    with path.open("rb") as stream:
        head = stream.read(_EXPORT_HEADER_BYTES)
    for line in head.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return stripped == "OPTION IMPORT;"
    return False


async def export_database(db: AsyncWsSurrealConnection, target: Path) -> None:
    """Stream the selected database to `target`; reject anything that cannot be re-imported."""
    await db.export_to(target)
    if not _has_import_header(target):
        raise MigrationError("Database export lacks the OPTION IMPORT header")


async def import_database(db: AsyncWsSurrealConnection, source: Path) -> None:
    await db.import_(source)


async def server_version(db: AsyncWsSurrealConnection) -> str | None:
    try:
        return str(await db.version())
    except Exception:
        return None


async def is_empty(db: AsyncWsSurrealConnection) -> bool:
    info = (await checked_query(db, "INFO FOR DB;"))[0]
    if not isinstance(info, dict):
        raise MigrationError("Cannot read database definitions")
    return all(not value for value in info.values())


async def table_counts(db: AsyncWsSurrealConnection) -> dict[str, int]:
    info = (await checked_query(db, "INFO FOR DB;"))[0]
    if not isinstance(info, dict) or not isinstance(info.get("tables"), dict):
        raise MigrationError("Cannot read database tables")
    counts: dict[str, int] = {}
    for table in sorted(info["tables"]):
        rows = (
            await checked_query(
                db, "SELECT count() AS n FROM $table GROUP ALL;", {"table": Table(table)}
            )
        )[0]
        counts[table] = int(rows[0]["n"]) if rows else 0
    return counts


async def ensure_database(db: AsyncWsSurrealConnection, database: str) -> None:
    await checked_query(db, "DEFINE DATABASE IF NOT EXISTS $database;", {"database": database})


async def recreate_empty(db: AsyncWsSurrealConnection, database: str) -> None:
    """Drop and redefine the selected database so an import starts from nothing."""
    await checked_query(db, "REMOVE DATABASE IF EXISTS $database;", {"database": database})
    await ensure_database(db, database)
    if not await is_empty(db):
        raise MigrationError("Database is not empty after recreation")
