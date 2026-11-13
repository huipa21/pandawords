from __future__ import annotations

import asyncio
import gzip
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db import backup
from app.db.migration_store import MigrationError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def connection(tables: dict[str, str] | None = None) -> AsyncMock:
    db = AsyncMock(spec=AsyncWsSurrealConnection)
    db.query_raw.return_value = {
        "result": [{"status": "OK", "result": {"tables": tables or {}, "users": {}}}]
    }
    db.export.return_value = "-- Export\nOPTION IMPORT;\nDEFINE TABLE example SCHEMAFULL;\n"
    return db


@pytest.mark.parametrize("tables", [{}, {"example": "DEFINE TABLE example SCHEMAFULL"}])
async def test_exports_fresh_and_existing_sites(tmp_path: Path, tables: dict[str, str]) -> None:
    db = connection(tables)
    first = await backup.backup_before_migrations(db, tmp_path)
    second = await backup.backup_before_migrations(db, tmp_path)
    assert first != second
    with gzip.open(first, "rt", encoding="utf-8") as stream:
        assert stream.read() == db.export.return_value
    assert sorted(await asyncio.to_thread(lambda: list(tmp_path.iterdir()))) == sorted(
        [first, second]
    )


@pytest.mark.parametrize("failure", ["export", "metadata", "invalid_export", "disk"])
async def test_backup_failure_prevents_migrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    db = connection()
    db.__aenter__.return_value = db
    monkeypatch.setattr(backup, "AsyncSurreal", lambda *args, **kwargs: db)
    migrations = AsyncMock()
    monkeypatch.setattr(backup, "run_migrations", migrations)
    if failure == "export":
        db.export.side_effect = RuntimeError("export unavailable")
    elif failure == "metadata":
        db.query_raw.return_value = {"result": [{"status": "ERR", "result": "denied"}]}
    elif failure == "invalid_export":
        db.export.return_value = ""
    else:
        tmp_path.joinpath("blocked").write_text("not a directory")
        tmp_path = tmp_path / "blocked"
    with pytest.raises((RuntimeError, MigrationError, OSError)):
        await backup.run(tmp_path)
    migrations.assert_not_awaited()


async def test_migrations_start_only_after_backup_is_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = connection()
    db.__aenter__.return_value = db
    monkeypatch.setattr(backup, "AsyncSurreal", lambda *args, **kwargs: db)

    async def migrate(connection: AsyncWsSurrealConnection) -> list[str]:
        assert connection is db
        files = await asyncio.to_thread(lambda: list(tmp_path.glob("*.surql.gz")))
        assert len(files) == 1
        with gzip.open(files[0], "rt", encoding="utf-8") as stream:
            assert stream.read() == db.export.return_value
        return []

    monkeypatch.setattr(backup, "run_migrations", migrate)
    await backup.run(tmp_path)
