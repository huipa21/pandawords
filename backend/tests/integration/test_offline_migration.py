import shutil
from pathlib import Path

import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db.auth import find_user
from app.db.dictionary_schema_test_support import table_info
from app.db.migrate import MIGRATIONS, discover, run_migrations
from app.db.migration_store import checked_query
from app.db.snapshot import snapshot
from tests.conftest import UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]


async def test_offline_guard_upgrade_replay_and_snapshot(
    db: AsyncWsSurrealConnection, make_user: UserFactory, tmp_path: Path
) -> None:
    prior = tmp_path / "migrations"
    prior.mkdir()
    for migration in discover(MIGRATIONS):
        if migration.version < "0026":
            shutil.copyfile(migration.path, prior / migration.path.name)
    await run_migrations(db, prior)
    user = await make_user()
    before = await find_user(db, user.id)
    applied = await run_migrations(db)
    assert applied[0] == "0026_offline_attempt_guard.surql"
    expected = await snapshot(db)
    assert await run_migrations(db) == []
    await checked_query(db, (MIGRATIONS / "0026_offline_attempt_guard.surql").read_text())
    assert await snapshot(db) == expected
    assert await find_user(db, user.id) == before
    info = await table_info(db, "offline_attempt_guard")
    assert "offline_attempt_guard_owner" in info["indexes"]
