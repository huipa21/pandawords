from datetime import UTC, datetime

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.security import create_access_token
from app.domain.identity import user_subject
from tests.api.auth_support import (
    NEW_PASSWORD,
    PASSWORD,
    assert_cookie_deleted,
    assert_invalid,
    bearer,
    login,
)
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_current_user_and_admin_use_database_identity(
    auth_client: AsyncClient, test_settings: Settings, make_user: UserFactory
) -> None:
    owner, admin = await make_user(), await make_user(role="admin")
    owner_login = await login(auth_client, owner.username)
    admin_login = await login(auth_client, admin.username)
    response = await auth_client.get("/api/test-auth/user", headers=bearer(owner_login))
    assert response.status_code == 200
    assert response.json() == {"id": owner.id, "role": "user"}
    rejected = await auth_client.get("/api/test-auth/admin", headers=bearer(owner_login))
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "auth.forbidden"
    allowed = await auth_client.get("/api/test-auth/admin", headers=bearer(admin_login))
    assert allowed.status_code == 200
    assert allowed.json() == {"id": admin.id}
    # Signed stale role claims cannot elevate a DB user or select someone else's identity.
    stale_role = create_access_token(owner.id, "admin", test_settings)
    headers = {"Authorization": f"Bearer {stale_role}"}
    assert (await auth_client.get("/api/test-auth/admin", headers=headers)).status_code == 403
    me = await auth_client.get(f"/api/auth/me?user_id={admin.id}", headers=headers)
    assert me.status_code == 200
    assert me.json()["id"] == owner.id
    assert me.json()["role"] == "user"


@pytest.mark.parametrize("kind", ["missing", "malformed", "tampered", "expired", "unknown"])
async def test_protected_endpoints_reject_invalid_bearer(
    auth_client: AsyncClient, test_settings: Settings, make_user: UserFactory, kind: str
) -> None:
    owner = await make_user()
    await login(auth_client, owner.username)
    token = create_access_token(owner.id, owner.role, test_settings)
    if kind == "malformed":
        token = "not-a-jwt"
    elif kind == "tampered":
        head, payload, signature = token.split(".")
        signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        token = ".".join((head, payload, signature))
    elif kind == "expired":
        now = int(datetime.now(UTC).timestamp())
        token = jwt.encode(
            {"sub": owner.id, "role": "user", "iat": now - 120, "exp": now - 60},
            test_settings.jwt_secret,
            algorithm="HS256",
        )
    elif kind == "unknown":
        # A valid JWT for a removed/nonexistent DB identity is not sufficient.
        token = create_access_token(user_subject("nonexistent_api_user"), "user", test_settings)
    headers = {} if kind == "missing" else {"Authorization": f"Bearer {token}"}
    for route in ("/api/auth/me", "/api/test-auth/user", "/api/test-auth/admin"):
        assert_invalid(await auth_client.get(route, headers=headers))
    assert_invalid(await auth_client.post("/api/auth/logout", headers=headers))
    assert_invalid(
        await auth_client.post(
            "/api/auth/password",
            headers=headers,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )
    )


async def test_logout_without_cookie_is_authenticated_and_idempotent(
    auth_client: AsyncClient, make_user: UserFactory
) -> None:
    owner = await make_user()
    first = await login(auth_client, owner.username)
    auth_client.cookies.clear()
    response = await auth_client.post("/api/auth/logout", headers=bearer(first))
    assert response.status_code == 204
    assert_cookie_deleted(response)
