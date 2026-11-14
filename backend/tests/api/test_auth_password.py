import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.security import decode_access_token
from app.db.auth_test_support import tokens_for
from tests.api.auth_support import (
    NEW_PASSWORD,
    PASSWORD,
    assert_cookie_deleted,
    assert_gate,
    assert_invalid,
    bearer,
    cookie_header,
    login,
    refresh_cookie,
)
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_forced_password_gate_allows_only_me_password_logout(
    auth_client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    owner = await make_user(role="admin", must_change_password=True)
    first = await login(auth_client, owner.username)
    headers = bearer(first)
    assert first.json()["user"]["must_change_password"] is True
    me = await auth_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["id"] == owner.id
    for path in ("/api/test-auth/user", "/api/test-auth/admin"):
        assert_gate(await auth_client.get(path, headers=headers))
    before = await tokens_for(db, owner.id)
    refresh = await auth_client.post(
        "/api/auth/refresh", headers=cookie_header(refresh_cookie(first))
    )
    assert_gate(refresh)
    assert_cookie_deleted(refresh)
    assert await tokens_for(db, owner.id) == before
    # Reaching password validation proves the gate did not block this exception.
    password = await auth_client.post(
        "/api/auth/password",
        headers=headers,
        json={"current_password": "incorrect-password", "new_password": NEW_PASSWORD},
    )
    assert_invalid(password)
    logout = await auth_client.post(
        "/api/auth/logout", headers=headers | cookie_header(refresh_cookie(first))
    )
    assert logout.status_code == 204
    assert_cookie_deleted(logout)


@pytest.mark.parametrize(
    ("current", "new", "status", "code"),
    [
        (PASSWORD, "123456789", 422, "validation.invalid"),
        ("incorrect-password", NEW_PASSWORD, 401, "auth.invalid_credentials"),
    ],
)
async def test_password_validation_does_not_mutate_user_or_sessions(
    auth_client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    current: str,
    new: str,
    status: int,
    code: str,
) -> None:
    owner = await make_user(must_change_password=True)
    first = await login(auth_client, owner.username)
    before = await tokens_for(db, owner.id)
    response = await auth_client.post(
        "/api/auth/password",
        headers=bearer(first),
        json={"current_password": current, "new_password": new},
    )
    assert response.status_code == status
    assert response.json()["code"] == code
    assert "set-cookie" not in response.headers
    assert await tokens_for(db, owner.id) == before
    me = await auth_client.get("/api/auth/me", headers=bearer(first))
    assert me.json()["must_change_password"] is True
    assert (await login(auth_client, owner.username)).status_code == 200


async def test_password_change_clears_gate_revokes_all_old_sessions_only_for_owner(
    auth_client: AsyncClient,
    db: AsyncWsSurrealConnection,
    test_settings: Settings,
    make_user: UserFactory,
) -> None:
    owner, other = await make_user(must_change_password=True), await make_user()
    first = await login(auth_client, owner.username)
    independent = await login(auth_client, owner.username)
    other_login = await login(auth_client, other.username)
    old_other_rows = await tokens_for(db, other.id)
    changed = await auth_client.post(
        "/api/auth/password",
        headers=bearer(first) | cookie_header(refresh_cookie(other_login)),
        json={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "user_id": other.id,
        },
    )
    headers = bearer(changed)
    assert changed.json()["user"]["id"] == owner.id
    assert changed.json()["user"]["must_change_password"] is False
    assert decode_access_token(changed.json()["access_token"], test_settings).sub == owner.id
    assert refresh_cookie(changed) not in {
        refresh_cookie(first),
        refresh_cookie(independent),
        refresh_cookie(other_login),
    }
    me = await auth_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["must_change_password"] is False
    protected = await auth_client.get("/api/test-auth/user", headers=headers)
    assert protected.status_code == 200
    assert protected.json()["id"] == owner.id
    # The gate is DB-backed even when the client still has its original access JWT.
    assert (await auth_client.get("/api/test-auth/user", headers=bearer(first))).status_code == 200
    for old in (first, independent):
        assert_invalid(
            await auth_client.post("/api/auth/refresh", headers=cookie_header(refresh_cookie(old)))
        )
    fresh = await auth_client.post(
        "/api/auth/refresh", headers=cookie_header(refresh_cookie(changed))
    )
    assert fresh.status_code == 200
    assert fresh.json()["user"]["id"] == owner.id
    assert await tokens_for(db, other.id) == old_other_rows
    assert (
        await auth_client.post(
            "/api/auth/refresh", headers=cookie_header(refresh_cookie(other_login))
        )
    ).status_code == 200
    assert (await login(auth_client, owner.username, NEW_PASSWORD)).status_code == 200
    assert_invalid(await login(auth_client, owner.username))
    assert (await login(auth_client, other.username)).status_code == 200
