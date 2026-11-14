import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid
from app.db import migrate, tags
from app.db.auth_schema_test_support import create_user
from app.domain.identity import user_subject
from app.domain.tags import TagCreate

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]


async def test_tag_revision_backfills_existing_users_without_resetting_replayed_state(
    db: AsyncWsSurrealConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migrations = migrate.discover(migrate.MIGRATIONS)
    with monkeypatch.context() as patch:
        patch.setattr(
            migrate,
            "discover",
            lambda _directory: [item for item in migrations if item.version < "0018"],
        )
        await migrate.run_migrations(db)
    row = await create_user(
        db,
        {
            "username": "legacy_tags",
            "password_hash": "unused-test-hash",
            "role": "user",
            "disabled": False,
            "must_change_password": False,
            "source_lang": "zh",
            "target_lang": "en",
            "prefs": {
                "theme": "dark",
                "locale": "en",
                "accent": "UK",
                "desired_retention": 0.95,
            },
        },
    )
    owner = user_subject(str(row["id"].id))
    assert await migrate.run_migrations(db) == [
        item.path.name for item in migrations if item.version >= "0018"
    ]
    a = await tags.create(db, owner, TagCreate(name="a"))
    b = await tags.create(db, owner, TagCreate(name="b"))
    await tags.assign(db, owner, decode_rid(b.id, "tag"), decode_rid(a.id, "tag"), remove=False)
    assert await migrate.run_migrations(db) == []
    assert len(await tags.memberships(db, owner, decode_rid(a.id, "tag"))) == 1
