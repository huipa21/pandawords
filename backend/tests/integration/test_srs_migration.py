import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db.auth import find_user
from app.db.auth_schema_test_support import create_user
from app.db.migrate import MIGRATIONS, discover, run_migrations
from app.domain.auth import UserPreferences
from app.domain.identity import user_subject
from app.domain.srs import SrsPreferences
from app.services import srs

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]


@pytest.fixture
def prior_migrations() -> Iterator[Path]:
    directory = Path(__file__).resolve().parents[2] / f".srs-migration-{uuid4().hex}"
    directory.mkdir()
    try:
        for migration in discover(MIGRATIONS):
            if migration.version < "0015":
                shutil.copyfile(migration.path, directory / migration.path.name)
        yield directory
    finally:
        shutil.rmtree(directory)


async def test_existing_preferences_backfill_and_replay_preserve_customization(
    db: AsyncWsSurrealConnection,
    prior_migrations: Path,
) -> None:
    await run_migrations(db, prior_migrations)
    row = await create_user(
        db,
        {
            "username": uuid4().hex,
            "password_hash": "test-only-hash",
            "role": "user",
            "disabled": False,
            "must_change_password": False,
            "source_lang": "zh",
            "target_lang": "en",
            "prefs": {"theme": "dark", "locale": "en", "accent": "UK"},
        },
    )
    owner = user_subject(str(row["id"].id))
    path = MIGRATIONS / "0015_srs_preferences.surql"
    shutil.copyfile(path, prior_migrations / path.name)
    assert await run_migrations(db, prior_migrations) == [path.name]
    loaded = await find_user(db, owner)
    assert loaded is not None
    assert loaded.prefs == UserPreferences(theme="dark", locale="en", accent="UK")
    assert (await srs.read_preferences(db, owner)).desired_retention == 0.9
    await srs.update_preferences(db, owner, SrsPreferences(desired_retention=0.97))
    assert await run_migrations(db, prior_migrations) == []
    loaded = await find_user(db, owner)
    assert loaded is not None
    assert loaded.prefs == UserPreferences(
        theme="dark",
        locale="en",
        accent="UK",
        desired_retention=0.97,
    )
