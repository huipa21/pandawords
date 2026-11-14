import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid
from app.db import migrate, tags
from app.domain.tags import TagCreate
from tests.conftest import UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]


async def test_tag_revision_backfills_existing_users_without_resetting_replayed_state(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migrations = migrate.discover(migrate.MIGRATIONS)
    with monkeypatch.context() as patch:
        patch.setattr(migrate, "discover", lambda _directory: migrations[:-1])
        await migrate.run_migrations(db)
    user = await make_user()
    assert await migrate.run_migrations(db) == ["0018_tag_hierarchy.surql"]
    a = await tags.create(db, user.id, TagCreate(name="a"))
    b = await tags.create(db, user.id, TagCreate(name="b"))
    await tags.assign(db, user.id, decode_rid(b.id, "tag"), decode_rid(a.id, "tag"), remove=False)
    assert await migrate.run_migrations(db) == []
    assert len(await tags.memberships(db, user.id, decode_rid(a.id, "tag"))) == 1
