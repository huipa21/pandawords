"""Forward-only migrations. Run from backend: python -m app.db.migrate [--dry-run]."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import inspect
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.client import database_lifespan
from app.db.migration_store import (
    TRACKING_SCHEMA,
    MigrationConnection,
    MigrationError,
    applied_migrations,
    checked_query,
)

MIGRATIONS = Path(__file__).with_name("migrations")
FILE_PATTERN = re.compile(r"(?P<version>\d{4})_[a-z0-9_]+\.(surql|py)")


@dataclass(frozen=True)
class Migration:
    path: Path
    version: str
    content: bytes

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def discover(directory: Path) -> list[Migration]:
    migrations: dict[str, Migration] = {}
    for path in sorted(directory.iterdir()):
        match = FILE_PATTERN.fullmatch(path.name)
        if not path.is_file() or match is None:
            continue
        version = match["version"]
        if version in migrations:
            raise MigrationError(f"Duplicate migration version {version}: {path.name}")
        migrations[version] = Migration(path, version, path.read_bytes())
    return sorted(migrations.values(), key=lambda migration: migration.version)


async def _apply(db: AsyncWsSurrealConnection, migration: Migration) -> None:
    txn = await db.begin()
    connection = MigrationConnection(db, txn)
    try:
        if migration.path.suffix == ".surql":
            await connection.query(migration.content.decode("utf-8"))
        else:
            spec = importlib.util.spec_from_file_location(
                f"_pandawords_migration_{migration.version}", migration.path
            )
            if spec is None:
                raise MigrationError(f"Cannot load {migration.path.name}")
            module = importlib.util.module_from_spec(spec)
            # Execute exactly the bytes whose checksum was calculated, never a stale .pyc.
            exec(compile(migration.content, str(migration.path), "exec"), module.__dict__)
            up = getattr(module, "up", None)
            if not inspect.iscoroutinefunction(up):
                raise MigrationError("Python migrations require async def up(db)")
            await up(connection)
        if connection.failed:
            raise MigrationError("Migration caught a failed database query; refusing to commit")
        await connection.query(
            "CREATE $id CONTENT {version: $version, name: $name, checksum: $checksum, "
            "applied_at: time::now()};",
            {
                "id": RecordID("_migration", migration.version),
                "version": migration.version,
                "name": migration.path.name,
                "checksum": migration.checksum,
            },
        )
        await db.commit(txn)
    except BaseException as exc:
        try:
            await db.cancel(txn)
        except Exception as cancel_error:
            exc.add_note(f"Transaction cancellation failed: {cancel_error}")
        if isinstance(exc, Exception):
            raise MigrationError(f"{migration.path.name}: {exc}") from exc
        raise


async def run_migrations(
    db: AsyncWsSurrealConnection,
    directory: Path = MIGRATIONS,
    *,
    dry_run: bool = False,
) -> list[str]:
    migrations = discover(directory)
    files = {migration.version: migration for migration in migrations}
    applied = await applied_migrations(db)
    for row in applied:
        migration = files.get(row["version"])
        if migration is None:
            raise MigrationError(f"Applied migration is missing: {row['name']}")
        if row["checksum"] != migration.checksum or row["name"] != migration.path.name:
            raise MigrationError(f"Checksum/name mismatch for applied migration {row['name']}")
    versions = {row["version"] for row in applied}
    pending = [migration for migration in migrations if migration.version not in versions]
    if not dry_run:
        await checked_query(db, TRACKING_SCHEMA)
        for migration in pending:
            await _apply(db, migration)
    return [migration.path.name for migration in pending]


async def _run_cli(dry_run: bool) -> None:
    settings = Settings()
    async with database_lifespan(settings) as database:
        db = await database.get_connection()
        if not isinstance(db, AsyncWsSurrealConnection):
            raise MigrationError("Migrations require a WebSocket connection with UUID transactions")
        names = await run_migrations(db, dry_run=dry_run)
    for name in names:
        print(f"{'Pending' if dry_run else 'Applied'}: {name}")
    if not names:
        print("No pending migrations.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate and list without applying")
    args = parser.parse_args()
    try:
        asyncio.run(_run_cli(args.dry_run))
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
