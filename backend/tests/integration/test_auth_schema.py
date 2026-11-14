from datetime import UTC, datetime, timedelta

import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.auth_schema_test_support import create_refresh_token, create_user
from app.db.migrate import run_migrations
from app.db.migration_store import MigrationError

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]


@pytest.fixture
async def auth_db(db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    await run_migrations(db)
    return db


@pytest.fixture
def user_attributes() -> dict[str, Value]:
    return {
        "username": "schema-test",
        "password_hash": "opaque-test-hash",
        "role": "user",
        "disabled": False,
        "must_change_password": True,
        "source_lang": "zh",
        "target_lang": "en",
        "prefs": {"theme": "system", "locale": "zh-CN", "accent": "US"},
    }


async def test_duplicate_username_rejected(
    auth_db: AsyncWsSurrealConnection, user_attributes: dict[str, Value]
) -> None:
    first = await create_user(auth_db, user_attributes)
    assert {key: first[key] for key in user_attributes if key != "prefs"} == {
        key: value for key, value in user_attributes.items() if key != "prefs"
    }
    assert first["prefs"]["desired_retention"] == 0.9
    assert first["prefs"]["review_images_enabled"] is True
    assert first["prefs"]["review_audio_enabled"] is True
    assert {
        key: value
        for key, value in first["prefs"].items()
        if key not in {"desired_retention", "review_images_enabled", "review_audio_enabled"}
    } == user_attributes["prefs"]
    with pytest.raises(MigrationError, match="user_username"):
        await create_user(auth_db, user_attributes)
    other = await create_user(auth_db, {**user_attributes, "username": "other", "role": "admin"})
    assert other["id"] != first["id"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role", "superuser"),
        ("disabled", "false"),
        ("prefs", {"theme": "invalid", "locale": "en", "accent": "US"}),
        ("prefs", {"theme": "dark", "locale": "en", "accent": "invalid"}),
    ],
)
async def test_user_field_constraints(
    auth_db: AsyncWsSurrealConnection,
    user_attributes: dict[str, Value],
    field: str,
    value: Value,
) -> None:
    with pytest.raises(MigrationError):
        await create_user(auth_db, {**user_attributes, field: value})


async def test_refresh_hash_unique_and_rotation_fields_round_trip(
    auth_db: AsyncWsSurrealConnection, user_attributes: dict[str, Value]
) -> None:
    user = await create_user(auth_db, user_attributes)
    expires = datetime.now(UTC) + timedelta(days=1)
    attributes: dict[str, Value] = {
        "user": user["id"],
        "token_hash": "a" * 64,
        "expires_at": expires,
    }
    successor = await create_refresh_token(auth_db, attributes)
    assert successor["user"] == user["id"]
    assert successor["expires_at"] == expires
    assert successor.get("revoked_at") is None
    assert successor.get("replaced_by") is None
    with pytest.raises(MigrationError, match="refresh_token_hash"):
        await create_refresh_token(auth_db, attributes)
    revoked_at = datetime.now(UTC)
    previous = await create_refresh_token(
        auth_db,
        {
            **attributes,
            "token_hash": "b" * 64,
            "revoked_at": revoked_at,
            "replaced_by": successor["id"],
        },
    )
    assert previous["revoked_at"] == revoked_at
    assert previous["replaced_by"] == successor["id"]
    for invalid in (
        {"user": RecordID("refresh_token", "wrong-table")},
        {"replaced_by": user["id"]},
        {"expires_at": "not-a-datetime"},
    ):
        with pytest.raises(MigrationError):
            await create_refresh_token(auth_db, {**attributes, "token_hash": "c" * 64, **invalid})
