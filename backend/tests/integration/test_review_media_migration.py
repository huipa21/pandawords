import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db import auth, migrate
from app.db.dictionary_schema_test_support import create
from app.db.migration_store import checked_query
from app.domain.auth import UserCreate, UserPreferences
from app.services import review_preferences

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]


async def test_existing_users_backfilled_and_replay_preserves_preferences(
    db: AsyncWsSurrealConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discover = migrate.discover
    with monkeypatch.context() as patch:
        patch.setattr(
            migrate,
            "discover",
            lambda path: [item for item in discover(path) if item.version < "0020"],
        )
        await migrate.run_migrations(db)
    data = UserCreate(
        username="legacy_media",
        password="legacy-test-password",
        prefs=UserPreferences(theme="dark", locale="en", accent="UK", desired_retention=0.95),
    ).model_dump(exclude={"password"})
    data["prefs"].pop("review_images_enabled")
    data["prefs"].pop("review_audio_enabled")
    await create(
        db, RecordID("user", "legacy_media"), {**data, "password_hash": "unused-test-hash"}
    )
    user = await auth.find_by_username(db, "legacy_media")
    assert user is not None
    await migrate.run_migrations(db)
    stored = await auth.find_user(db, user.id)
    assert stored is not None
    assert stored.prefs.model_dump() == {
        "theme": "dark",
        "locale": "en",
        "accent": "UK",
        "desired_retention": 0.95,
        "review_images_enabled": True,
        "review_audio_enabled": True,
    }
    from app.domain.review_preferences import ReviewPreferencesUpdate

    await review_preferences.update(
        db,
        user.id,
        ReviewPreferencesUpdate(review_images_enabled=False, review_audio_enabled=False),
    )
    await checked_query(
        db, (migrate.MIGRATIONS / "0020_review_media_preferences.surql").read_text("utf-8")
    )
    prefs = await review_preferences.read(db, user.id)
    assert (
        not prefs.review_images_enabled and not prefs.review_audio_enabled and prefs.accent == "UK"
    )
