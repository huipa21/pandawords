from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.client import database_lifespan
from app.db.migrate import MIGRATIONS, run_migrations
from app.db.migration_test_support import SUCCESS, remove_database
from app.db.snapshot import SNAPSHOT, snapshot
from tests.snapshot_plugin import assert_snapshot

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
async def snapshot_db() -> AsyncIterator[AsyncWsSurrealConnection]:
    settings = Settings()
    url = urlsplit(settings.surreal_test_url)
    assert url.port == 8101 and url.hostname in {"127.0.0.1", "localhost", "::1"}, (
        "Schema snapshots require the loopback test server on 8101"
    )
    settings = settings.model_copy(
        update={
            "surreal_url": settings.surreal_test_url,
            "surreal_namespace": "pandawords_test",
            "surreal_database": f"t_snapshot_{uuid4().hex}",
        }
    )
    async with database_lifespan(settings) as database:
        db = await database.get_connection()
        assert isinstance(db, AsyncWsSurrealConnection)
        try:
            await run_migrations(db)
            yield db
        finally:
            await remove_database(db, settings.surreal_database)


@pytest.fixture
def snapshot_directory() -> Iterator[Path]:
    directory = BACKEND / f".snapshot-test-{uuid4().hex}"
    directory.mkdir()
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


async def test_schema_snapshot(
    snapshot_db: AsyncWsSurrealConnection, update_snapshot: bool
) -> None:
    assert_snapshot(await snapshot(snapshot_db), SNAPSHOT, update=update_snapshot)


async def test_new_migration_fails_with_readable_table_and_field_diff(
    snapshot_db: AsyncWsSurrealConnection, snapshot_directory: Path
) -> None:
    before = await snapshot(snapshot_db)
    baseline = snapshot_directory / "schema.snapshot.json"
    assert_snapshot(before, baseline, update=True)
    migrations = snapshot_directory / "migrations"
    shutil.copytree(MIGRATIONS, migrations)
    (migrations / "9999_snapshot_probe.surql").write_text(SUCCESS, encoding="utf-8")
    await run_migrations(snapshot_db, migrations)
    actual = await snapshot(snapshot_db)
    with pytest.raises(pytest.fail.Exception) as failure:
        assert_snapshot(actual, baseline)
    message = str(failure.value)
    assert "--- schema.snapshot.json (committed)" in message
    assert "+++ schema.snapshot.json (migrated)" in message
    assert '+      "migration_probe":' in message
    metadata = json.loads(actual)
    field = metadata["tables"]["migration_probe"]["fields"]["value"]
    assert any(line.startswith("+") and json.dumps(field) in line for line in message.splitlines())
    assert "-UpdateSnapshot" in message
    assert baseline.read_text(encoding="utf-8") == before

    assert_snapshot(actual, baseline, update=True)
    assert_snapshot(await snapshot(snapshot_db), baseline)
    assert await snapshot(snapshot_db) == actual
    assert "fields" in metadata["tables"]["_migration"]
    assert "migration_version" in metadata["tables"]["_migration"]["indexes"]
