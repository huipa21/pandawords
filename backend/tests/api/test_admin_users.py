import asyncio
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from surrealdb import AsyncSurrealConnection
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.errors import AppError
from app.core.security import verify_password
from app.db import admin as repository
from app.db.auth import find_user
from app.db.migrate import run_migrations
from app.domain.admin import AdminUserUpdate
from app.services import admin
from tests.api.auth_support import bearer, cookie_header, login, refresh_cookie
from tests.conftest import UserFactory


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH"])
async def test_nonadmin_cannot_administer(
    client: AsyncClient, make_user: UserFactory, method: str
) -> None:
    user = await make_user()
    other = await make_user()
    headers = bearer(await login(client, user.username))
    url = "/api/admin/users" + (f"/{other.id}" if method == "PATCH" else "")
    response = await client.request(method, url, headers=headers, json={})
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


async def test_list_pagination_is_credential_free(
    client: AsyncClient, make_user: UserFactory
) -> None:
    actor = await make_user(role="admin")
    await make_user()
    headers = bearer(await login(client, actor.username))
    first = await client.get("/api/admin/users?page_size=1", headers=headers)
    second = await client.get("/api/admin/users?page=2&page_size=1", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] >= 3
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
    assert set(first.json()["items"][0]) == {
        "id",
        "username",
        "role",
        "disabled",
        "must_change_password",
        "source_lang",
        "target_lang",
        "prefs",
    }
    assert first.headers["cache-control"] == "no-store"
    beyond = await client.get("/api/admin/users?page=999999", headers=headers)
    assert beyond.json()["items"] == []
    for query in ("page=0", "page_size=0", "page_size=101"):
        assert (await client.get(f"/api/admin/users?{query}", headers=headers)).status_code == 422


@pytest.mark.parametrize("role", ["user", "admin"])
async def test_create_temporary_password_forced_and_unique(
    client: AsyncClient, make_user: UserFactory, db: AsyncWsSurrealConnection, role: str
) -> None:
    actor = await make_user(role="admin")
    headers = bearer(await login(client, actor.username))
    username = f"created_{uuid4().hex}"
    response = await client.post(
        "/api/admin/users", headers=headers, json={"username": username, "role": role}
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["user"]["must_change_password"] is True
    assert result["user"]["role"] == role
    assert "password_hash" not in result["user"]
    assert response.headers["cache-control"] == "no-store"
    stored = await find_user(db, result["user"]["id"])
    assert stored is not None
    assert stored.password_hash != result["temporary_password"]
    assert verify_password(result["temporary_password"], stored.password_hash)
    signed_in = await login(client, username, result["temporary_password"])
    assert signed_in.status_code == 200
    gate = await client.get("/api/admin/users", headers=bearer(signed_in))
    assert gate.status_code == 403
    assert gate.json()["code"] == "auth.password_change_required"
    duplicate = await client.post("/api/admin/users", headers=headers, json={"username": username})
    assert duplicate.status_code == 409
    extra = await client.post(
        "/api/admin/users",
        headers=headers,
        json={"username": username, "password": "chosen", "must_change_password": False},
    )
    assert extra.status_code == 422


@pytest.mark.parametrize(
    "change", [{"disabled": True}, {"role": "admin"}, {"role": "user"}, {"reset_password": True}]
)
async def test_patch_revokes_refresh_and_updates_live_authorization(
    client: AsyncClient, make_user: UserFactory, db: AsyncWsSurrealConnection, change: dict
) -> None:
    actor = await make_user(role="admin")
    target = await make_user(role="admin" if change.get("role") == "user" else "user")
    target_login = await login(client, target.username)
    actor_headers = bearer(await login(client, actor.username))
    response = await client.patch(
        f"/api/admin/users/{target.id}", headers=actor_headers, json=change
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert "password_hash" not in result["user"]
    revoked = await client.post(
        "/api/auth/refresh", headers=cookie_header(refresh_cookie(target_login))
    )
    assert revoked.status_code == 401
    if change.get("reset_password"):
        temporary = result["temporary_password"]
        stored = await find_user(db, target.id)
        assert stored is not None and verify_password(temporary, stored.password_hash)
        assert result["user"]["must_change_password"] is True
        gated = await client.get("/api/admin/users", headers=bearer(target_login))
        assert gated.status_code == 403
        assert gated.json()["code"] == "auth.password_change_required"
        assert (await login(client, target.username, temporary)).status_code == 200
        assert (await login(client, target.username)).status_code == 401
    else:
        assert result["temporary_password"] is None
    if "role" in change:
        permitted = await client.get("/api/admin/users", headers=bearer(target_login))
        assert permitted.status_code == (200 if change["role"] == "admin" else 403)
    if change.get("disabled"):
        assert (await client.get("/api/auth/me", headers=bearer(target_login))).status_code == 401
        enabled = await client.patch(
            f"/api/admin/users/{target.id}", headers=actor_headers, json={"disabled": False}
        )
        assert enabled.status_code == 200
        assert (await login(client, target.username)).status_code == 200


@pytest.mark.parametrize("change", [{"disabled": True}, {"role": "user"}])
async def test_self_and_disabled_admin_guards(
    client: AsyncClient, make_user: UserFactory, change: dict
) -> None:
    actor = await make_user(role="admin")
    disabled = await make_user(role="admin", disabled=True)
    headers = bearer(await login(client, actor.username))
    protected = await client.patch(f"/api/admin/users/{actor.id}", headers=headers, json=change)
    assert protected.status_code == 409
    assert protected.json()["code"] == "admin.self_protected"
    # A disabled admin is not counted as an enabled admin, and can be demoted.
    demoted = await client.patch(
        f"/api/admin/users/{disabled.id}", headers=headers, json={"role": "user"}
    )
    assert demoted.status_code == 200
    assert (await login(client, disabled.username)).status_code == 401


async def test_invalid_target_and_payload(client: AsyncClient, make_user: UserFactory) -> None:
    actor = await make_user(role="admin")
    headers = bearer(await login(client, actor.username))
    assert (
        await client.patch("/api/admin/users/invalid", headers=headers, json={"disabled": True})
    ).status_code == 404
    for body in ({"disabled": None}, {"role": None}, {"reset_password": None}, {"role": "root"}):
        assert (
            await client.patch(f"/api/admin/users/{actor.id}", headers=headers, json=body)
        ).status_code == 422


async def test_admin_permission_does_not_select_another_users_identity(
    client: AsyncClient, make_user: UserFactory
) -> None:
    actor = await make_user(role="admin")
    other = await make_user()
    headers = bearer(await login(client, actor.username))
    me = await client.get(f"/api/auth/me?user_id={other.id}&owner={other.id}", headers=headers)
    assert me.status_code == 200
    assert me.json()["id"] == actor.id
    assert "password_hash" not in me.json()
    # Account management does not grant a generic endpoint for another user's data.
    assert (await client.get(f"/api/admin/users/{other.id}", headers=headers)).status_code == 405


@pytest.mark.parametrize("change", [{"disabled": True}, {"role": "user"}])
@pytest.mark.fresh_db
async def test_two_admin_race_serialized(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
    change: dict,
) -> None:
    await run_migrations(db)
    first = await make_user(role="admin")
    second = await make_user(role="admin")
    await make_user(role="admin", disabled=True)
    original = repository._authorize
    ready = asyncio.Event()
    arrivals = 0
    attempts = 0

    async def synchronized(connection: AsyncSurrealConnection, actor: str, txn: UUID) -> None:
        nonlocal arrivals, attempts
        attempts += 1
        await original(connection, actor, txn)
        arrivals += 1
        if arrivals == 2:
            ready.set()
        if arrivals <= 2:
            await asyncio.wait_for(ready.wait(), 10)

    monkeypatch.setattr(repository, "_authorize", synchronized)
    results = await asyncio.gather(
        admin.update_user(db, first.id, second.id, AdminUserUpdate.model_validate(change)),
        admin.update_user(db, second.id, first.id, AdminUserUpdate.model_validate(change)),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, BaseException) for result in results) == 1, results
    failures = [result for result in results if isinstance(result, AppError)]
    assert len(failures) == 1 and failures[0].code == "auth.forbidden", results
    assert attempts >= 3
    users = [await find_user(db, first.id), await find_user(db, second.id)]
    assert (
        sum(user is not None and user.role == "admin" and not user.disabled for user in users) == 1
    )
