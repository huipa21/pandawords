from datetime import datetime
from http.cookies import SimpleCookie
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from surrealdb import AsyncSurrealConnection
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.security import decode_access_token, hash_refresh_token
from app.db.auth import issue_refresh
from app.db.auth_test_support import disable_user, tokens_for
from app.domain.auth import AuthTokens, PasswordChange, User
from app.main import create_app
from app.services.auth import change_password
from tests.api.auth_support import (
    COOKIE,
    NEW_PASSWORD,
    PASSWORD,
    assert_cookie_deleted,
    assert_invalid,
    bearer,
    cookie_header,
    login,
    refresh_cookie,
)
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_login_public_identity_and_cookie(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    test_settings: Settings,
    make_user: UserFactory,
) -> None:
    owner, other = await make_user(), await make_user()
    response = await login(client, owner.username)
    headers = bearer(response)
    body = response.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"], test_settings).sub == owner.id
    assert body["user"] == owner.model_dump(exclude={"password_hash"})
    assert "password_hash" not in response.text
    assert PASSWORD not in response.text
    assert owner.password_hash not in response.text
    token = refresh_cookie(response)
    assert token not in response.text
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    assert cookie[COOKIE]["httponly"]
    assert cookie[COOKIE]["samesite"].lower() == "strict"
    assert cookie[COOKIE]["path"] == "/api/auth"
    assert not cookie[COOKIE]["secure"]
    rows = await tokens_for(db, owner.id)
    assert rows[0]["token_hash"] == hash_refresh_token(token)
    assert token not in str(rows)
    # Caller-controlled IDs and another user's cookie cannot select the identity.
    other_login = await login(client, other.username)
    me = await client.get(
        f"/api/auth/me?user_id={other.id}",
        headers=headers | cookie_header(refresh_cookie(other_login)),
    )
    assert me.status_code == 200
    assert me.json() == body["user"]
    assert owner.password_hash not in me.text
    assert other.id not in me.text


async def test_bad_credentials_are_generic(client: AsyncClient, make_user: UserFactory) -> None:
    owner = await make_user()
    disabled = await make_user(disabled=True)
    unknown = f"missing_{owner.username}"
    responses = [
        await login(client, owner.username, "incorrect-password"),
        await login(client, unknown),
        await login(client, disabled.username),
    ]
    for response in responses:
        assert_invalid(response)
        assert "set-cookie" not in response.headers
    assert responses[0].json() == responses[1].json() == responses[2].json()


async def test_login_rejects_password_changed_after_verification_before_issuance(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    test_settings: Settings,
    make_user: UserFactory,
) -> None:
    owner = await make_user()
    concurrent_changes: list[AuthTokens] = []

    async def change_before_issue(
        connection: AsyncSurrealConnection,
        subject: str,
        token_hash: str,
        expires_at: datetime,
        expected_password_hash: str | None = None,
    ) -> User | None:
        concurrent_changes.append(
            await change_password(
                connection,
                test_settings,
                owner,
                PasswordChange(current_password=PASSWORD, new_password=NEW_PASSWORD),
            )
        )
        return await issue_refresh(
            connection, subject, token_hash, expires_at, expected_password_hash
        )

    with patch("app.services.auth.repository.issue_refresh", side_effect=change_before_issue):
        response = await login(client, owner.username)
    assert_invalid(response)
    assert "set-cookie" not in response.headers
    assert len(concurrent_changes) == 1
    rows = await tokens_for(db, owner.id)
    assert len(rows) == 1
    assert rows[0]["token_hash"] == hash_refresh_token(concurrent_changes[0].refresh_token)


async def test_cookie_is_secure_in_production(
    db: AsyncWsSurrealConnection, test_settings: Settings, make_user: UserFactory
) -> None:
    owner = await make_user()
    application = create_app(test_settings.model_copy(update={"app_env": "production"}))
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="https://test"
        ) as client:
            response = await login(client, owner.username)
            headers = bearer(response)
            cookie = SimpleCookie()
            cookie.load(response.headers["set-cookie"])
            assert cookie[COOKIE]["secure"]
            assert cookie[COOKIE]["httponly"]
            assert cookie[COOKIE]["samesite"].lower() == "strict"
            assert cookie[COOKIE]["path"] == "/api/auth"
            rotated = await client.post("/api/auth/refresh")
            assert rotated.status_code == 200
            assert refresh_cookie(rotated) != refresh_cookie(response)
            assert "Secure" in rotated.headers["set-cookie"]
            logout = await client.post("/api/auth/logout", headers=headers)
            assert logout.status_code == 204
            assert_cookie_deleted(logout)
            assert "Secure" in logout.headers["set-cookie"]


async def test_rotation_and_reuse_are_isolated(client: AsyncClient, make_user: UserFactory) -> None:
    owner, other = await make_user(), await make_user()
    first = await login(client, owner.username)
    independent = await login(client, owner.username)
    other_login = await login(client, other.username)
    second = await client.post(
        "/api/auth/refresh",
        headers=bearer(other_login) | cookie_header(refresh_cookie(first)),
    )
    assert second.status_code == 200
    assert second.json()["user"]["id"] == owner.id
    third = await client.post("/api/auth/refresh", headers=cookie_header(refresh_cookie(second)))
    assert third.status_code == 200
    assert len({refresh_cookie(first), refresh_cookie(second), refresh_cookie(third)}) == 3
    reused = await client.post("/api/auth/refresh", headers=cookie_header(refresh_cookie(first)))
    assert_invalid(reused)
    assert_cookie_deleted(reused)
    descendant = await client.post(
        "/api/auth/refresh", headers=cookie_header(refresh_cookie(third))
    )
    assert_invalid(descendant)
    for response in (independent, other_login):
        alive = await client.post(
            "/api/auth/refresh", headers=cookie_header(refresh_cookie(response))
        )
        assert alive.status_code == 200
        assert alive.json()["user"]["id"] == response.json()["user"]["id"]


async def test_logout_revokes_own_family_not_other_sessions(
    client: AsyncClient, make_user: UserFactory
) -> None:
    owner, other = await make_user(), await make_user()
    first = await login(client, owner.username)
    independent = await login(client, owner.username)
    other_login = await login(client, other.username)
    rotated = await client.post("/api/auth/refresh", headers=cookie_header(refresh_cookie(first)))
    logout = await client.post(
        "/api/auth/logout", headers=bearer(first) | cookie_header(refresh_cookie(first))
    )
    assert logout.status_code == 204
    assert logout.content == b""
    assert_cookie_deleted(logout)
    assert_invalid(
        await client.post("/api/auth/refresh", headers=cookie_header(refresh_cookie(rotated)))
    )
    repeated = await client.post(
        "/api/auth/logout", headers=bearer(first) | cookie_header(refresh_cookie(first))
    )
    assert repeated.status_code == 204
    for response in (independent, other_login):
        assert (
            await client.post("/api/auth/refresh", headers=cookie_header(refresh_cookie(response)))
        ).status_code == 200


async def test_logout_does_not_revoke_another_users_cookie(
    client: AsyncClient, make_user: UserFactory
) -> None:
    owner, other = await make_user(), await make_user()
    owner_login = await login(client, owner.username)
    other_login = await login(client, other.username)
    response = await client.post(
        "/api/auth/logout",
        headers=bearer(owner_login) | cookie_header(refresh_cookie(other_login)),
    )
    assert response.status_code == 204
    assert_cookie_deleted(response)
    assert (
        await client.post("/api/auth/refresh", headers=cookie_header(refresh_cookie(other_login)))
    ).status_code == 200


async def test_disabled_user_rejected_after_jwt_and_cookie_issuance(
    auth_client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    owner = await make_user()
    first = await login(auth_client, owner.username)
    await disable_user(db, owner.id)
    for route in ("/api/auth/me", "/api/test-auth/user", "/api/test-auth/admin"):
        assert_invalid(await auth_client.get(route, headers=bearer(first)))
    assert_invalid(
        await auth_client.post("/api/auth/refresh", headers=cookie_header(refresh_cookie(first)))
    )
    assert_invalid(
        await auth_client.post(
            "/api/auth/password",
            headers=bearer(first),
            json={"current_password": PASSWORD, "new_password": "replacement-password"},
        )
    )
    assert_invalid(await auth_client.post("/api/auth/logout", headers=bearer(first)))


@pytest.mark.parametrize("token", [None, "invalid", "", "x" * 43])
async def test_refresh_rejects_missing_malformed_or_unknown_cookie(
    client: AsyncClient, token: str | None
) -> None:
    client.cookies.clear()
    response = await client.post(
        "/api/auth/refresh", headers=cookie_header(token) if token is not None else {}
    )
    assert_invalid(response)
    if token is not None:
        assert_cookie_deleted(response)
