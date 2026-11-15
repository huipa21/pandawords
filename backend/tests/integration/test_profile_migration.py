import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db import auth, migrate, profile
from app.db.dictionary_schema_test_support import create
from app.db.migration_store import checked_query
from app.domain.auth import UserCreate
from app.domain.profile import ProfileUpdate

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]


async def test_legacy_users_backfilled_and_replay_preserves_profile(
    db: AsyncWsSurrealConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    discover = migrate.discover
    with monkeypatch.context() as patch:
        patch.setattr(
            migrate,
            "discover",
            lambda path: [item for item in discover(path) if item.version < "0028"],
        )
        await migrate.run_migrations(db)
    data = UserCreate(
        username="legacy_profile", password="legacy-test-password", must_change_password=False
    ).model_dump(exclude={"password"})
    await create(
        db, RecordID("user", "legacy_profile"), {**data, "password_hash": "unused-test-hash"}
    )
    legacy = await auth.find_by_username(db, "legacy_profile")
    assert legacy is not None
    assert (legacy.email, legacy.full_name, legacy.avatar) == ("", "", "")
    assert await migrate.run_migrations(db) == ["0028_user_profile.surql"]
    stored = await auth.find_user(db, legacy.id)
    assert stored == legacy
    fields = ProfileUpdate(full_name="Legacy Learner", email="legacy@example.com", avatar="")
    updated = await profile.update_profile(db, legacy.id, fields)
    assert updated is not None
    assert updated.model_dump() == {**legacy.model_dump(), **fields.model_dump()}
    await checked_query(db, (migrate.MIGRATIONS / "0028_user_profile.surql").read_text("utf-8"))
    assert await auth.find_user(db, legacy.id) == updated
    assert await migrate.run_migrations(db) == []
