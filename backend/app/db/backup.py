"""Fail-closed pre-migration SDK export. Run: python -m app.db.backup."""

from __future__ import annotations

import argparse
import asyncio
import gzip
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import structlog
from surrealdb import AsyncSurreal
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.migrate import run_migrations
from app.db.migration_store import MigrationError, checked_query


def _write_backup(directory: Path, exported: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = directory / f"pre-migrate-{stamp}-{uuid4().hex}.surql.gz"
    partial = destination.with_suffix(".partial")
    try:
        with gzip.open(partial, "xb") as stream:
            stream.write(exported.encode("utf-8"))
        partial.rename(destination)
    finally:
        partial.unlink(missing_ok=True)
    return destination


async def backup_before_migrations(db: AsyncWsSurrealConnection, directory: Path) -> Path:
    info = (await checked_query(db, "INFO FOR DB;"))[0]
    if not isinstance(info, dict) or "tables" not in info:
        raise MigrationError("Cannot establish database state before backup")
    fresh = all(not value for value in info.values())
    # Even a fresh database is exported: no exception is treated as an empty site.
    exported = await db.export()
    if not isinstance(exported, str) or "OPTION IMPORT;" not in exported:
        raise MigrationError("Invalid SDK export; refusing to migrate")
    destination = await asyncio.to_thread(_write_backup, directory, exported)
    structlog.get_logger().info("pre_migration_backup_saved", fresh_database=fresh)
    return destination


async def run(directory: Path) -> None:
    settings = Settings()
    async with AsyncSurreal(settings.surreal_url, timeout=300) as db:
        if not isinstance(db, AsyncWsSurrealConnection):
            raise MigrationError("Backup/migrations require a WebSocket connection")
        await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
        await db.use(settings.surreal_namespace, settings.surreal_database)
        await backup_before_migrations(db, directory)
        names = await run_migrations(db)
        structlog.get_logger().info("migrations_completed", count=len(names))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, default=Path("/backups"))
    args = parser.parse_args()
    asyncio.run(run(args.backup_dir))


if __name__ == "__main__":
    main()
