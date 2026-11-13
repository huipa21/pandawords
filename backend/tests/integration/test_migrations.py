from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.client import database_lifespan
from app.db.migrate import MIGRATIONS, discover, run_migrations
from app.db.migration_store import MigrationError
from app.db.migration_test_support import (
    FAILURE,
    PYTHON_QUERY_FAILURE,
    PYTHON_RAISE,
    PYTHON_SUCCESS,
    PYTHON_SWALLOW,
    SUCCESS,
    history,
    invalidate_history_checksum,
    probe_value,
    remove_database,
    tables,
)

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def migration_directory() -> Iterator[Path]:
    directory = BACKEND / f".migration-test-{uuid4().hex}"
    directory.mkdir()
    try:
        shutil.copyfile(MIGRATIONS / "0001_bootstrap.surql", directory / "0001_bootstrap.surql")
        yield directory
    finally:
        shutil.rmtree(directory)


@pytest.fixture
def migration_settings() -> Settings:
    settings = Settings()
    assert urlsplit(settings.surreal_test_url).port == 8101, "Use only the test server on 8101"
    return settings.model_copy(
        update={
            "surreal_url": settings.surreal_test_url,
            "surreal_namespace": "pandawords_test",
            "surreal_database": f"t_migration_{uuid4().hex}",
        }
    )


@pytest.fixture
async def db(migration_settings: Settings) -> AsyncIterator[AsyncWsSurrealConnection]:
    async with database_lifespan(migration_settings) as database:
        connection = await database.get_connection()
        assert isinstance(connection, AsyncWsSurrealConnection)
        try:
            yield connection
        finally:
            await remove_database(connection, migration_settings.surreal_database)


async def test_fresh_apply_noop_and_read_only_dry_run(db: AsyncWsSurrealConnection) -> None:
    expected = [migration.path.name for migration in discover(MIGRATIONS)]
    assert await run_migrations(db, dry_run=True) == expected
    assert await tables(db) == {}
    assert await run_migrations(db) == expected
    before = await history(db)
    assert len(before) == len(expected)
    assert before[0]["version"] == "0001"
    assert before[0]["checksum"] == discover(MIGRATIONS)[0].checksum
    assert before[0]["applied_at"] is not None
    assert await run_migrations(db) == []
    assert await run_migrations(db, dry_run=True) == []
    assert await history(db) == before


async def test_edited_applied_file_blocks_all_pending(
    db: AsyncWsSurrealConnection, migration_directory: Path
) -> None:
    await run_migrations(db, migration_directory)
    path = migration_directory / "0001_bootstrap.surql"
    path.write_bytes(path.read_bytes() + b"\n-- edited\n")
    (migration_directory / "0002_probe.surql").write_text(SUCCESS, encoding="utf-8")
    for dry_run in (False, True):
        with pytest.raises(MigrationError, match="Checksum/name mismatch.*0001_bootstrap"):
            await run_migrations(db, migration_directory, dry_run=dry_run)
    assert "migration_probe" not in await tables(db)
    assert len(await history(db)) == 1


@pytest.mark.parametrize(
    ("name", "script", "message"),
    [
        ("0002_failure.surql", FAILURE, "intentional_migration_failure"),
        ("0002_raise.py", PYTHON_RAISE, "intentional_python_failure"),
        ("0002_query.py", PYTHON_QUERY_FAILURE, "python_query_failure"),
        ("0002_swallow.py", PYTHON_SWALLOW, "refusing to commit"),
        ("0002_sync.py", "def up(db): pass\n", "require async def up"),
    ],
)
async def test_failed_migration_rolls_back_schema_data_and_marker(
    db: AsyncWsSurrealConnection,
    migration_directory: Path,
    name: str,
    script: str,
    message: str,
) -> None:
    await run_migrations(db, migration_directory)
    before = await history(db)
    (migration_directory / name).write_text(script, encoding="utf-8")
    with pytest.raises(MigrationError, match=message):
        await run_migrations(db, migration_directory)
    assert "migration_probe" not in await tables(db)
    assert await history(db) == before
    # A corrected, never-applied file can be retried on the same connection.
    (migration_directory / name).write_text(
        SUCCESS if name.endswith(".surql") else PYTHON_SUCCESS, encoding="utf-8"
    )
    assert await run_migrations(db, migration_directory) == [name]
    assert await probe_value(db) == ("written" if name.endswith(".surql") else "python")
    assert len(await history(db)) == 2


async def test_python_success_and_order(
    db: AsyncWsSurrealConnection, migration_directory: Path
) -> None:
    (migration_directory / "0003_python.py").write_text(PYTHON_SUCCESS, encoding="utf-8")
    (migration_directory / "0002_empty.surql").write_text("-- no changes\n", encoding="utf-8")
    assert await run_migrations(db, migration_directory) == [
        "0001_bootstrap.surql",
        "0002_empty.surql",
        "0003_python.py",
    ]
    assert await probe_value(db) == "python"
    assert await run_migrations(db, migration_directory) == []


async def test_missing_applied_file_and_duplicate_version_rejected(
    db: AsyncWsSurrealConnection, migration_directory: Path
) -> None:
    await run_migrations(db, migration_directory)
    (migration_directory / "0001_bootstrap.surql").unlink()
    with pytest.raises(MigrationError, match="Applied migration is missing"):
        await run_migrations(db, migration_directory)
    (migration_directory / "0002_one.surql").write_text(SUCCESS, encoding="utf-8")
    (migration_directory / "0002_two.py").write_text(PYTHON_SUCCESS, encoding="utf-8")
    with pytest.raises(MigrationError, match="Duplicate migration version 0002"):
        await run_migrations(db, migration_directory)


async def test_cli_dry_run_apply_and_noop(
    db: AsyncWsSurrealConnection,
    migration_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "surreal_url",
        "surreal_namespace",
        "surreal_database",
        "surreal_user",
        "surreal_pass",
    ):
        monkeypatch.setenv(key.upper(), str(getattr(migration_settings, key)))
    migration_names = [migration.path.name for migration in discover(MIGRATIONS)]
    for arguments, expected in (
        (["--dry-run"], [f"Pending: {name}" for name in migration_names]),
        ([], [f"Applied: {name}" for name in migration_names]),
        ([], ["No pending migrations."]),
    ):
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "app.db.migrate", *arguments],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert all(line in result.stdout.splitlines() for line in expected)
        if arguments:
            assert await tables(db) == {}
    assert len(await history(db)) == len(discover(MIGRATIONS))
    await invalidate_history_checksum(db)
    failure = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "app.db.migrate"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert failure.returncode == 1
    assert "Migration failed: Checksum/name mismatch" in failure.stderr
