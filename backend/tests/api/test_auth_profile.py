import base64
import io

import pytest
from httpx import AsyncClient
from PIL import Image

from tests.api.auth_support import assert_invalid, bearer, cookie_header, login, refresh_cookie
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


def avatar(format: str = "PNG") -> str:
    content = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(content, format=format)
    mime = {"PNG": "png", "JPEG": "jpeg", "WEBP": "webp"}[format]
    return f"data:image/{mime};base64,{base64.b64encode(content.getvalue()).decode()}"


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
async def test_profile_persists_and_is_isolated(
    client: AsyncClient, make_user: UserFactory, format: str
) -> None:
    owner, other = await make_user(), await make_user()
    headers = bearer(await login(client, owner.username))
    data = {
        "full_name": "  Panda Learner  ",
        "email": "  learner@example.com  ",
        "avatar": avatar(format),
    }
    expected = {**data, "full_name": "Panda Learner", "email": "learner@example.com"}
    response = await client.patch(
        f"/api/auth/me/profile?user_id={other.id}", json=data, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {**owner.model_dump(exclude={"password_hash"}), **expected}
    me = await client.get("/api/auth/me", headers=headers)
    assert me.json() == response.json()
    relogin = await login(client, owner.username)
    assert relogin.json()["user"] == response.json()
    refreshed = await client.post(
        "/api/auth/refresh", headers=cookie_header(refresh_cookie(relogin))
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["user"] == response.json()
    other_login = await login(client, other.username)
    assert other_login.json()["user"] == other.model_dump(exclude={"password_hash"})
    cleared = await client.patch(
        "/api/auth/me/profile",
        json={"full_name": "", "email": "", "avatar": ""},
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.json() == owner.model_dump(exclude={"password_hash"})


async def test_profile_requires_authentication(client: AsyncClient, make_user: UserFactory) -> None:
    data = {"full_name": "", "email": "", "avatar": ""}
    for headers in ({}, {"Authorization": "Bearer invalid"}):
        assert_invalid(await client.patch("/api/auth/me/profile", json=data, headers=headers))
    forced = await make_user(must_change_password=True)
    headers = bearer(await login(client, forced.username))
    response = await client.patch("/api/auth/me/profile", json=data, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "auth.password_change_required"


async def test_profile_requires_all_fields_and_strips_before_length_validation(
    client: AsyncClient, make_user: UserFactory
) -> None:
    owner = await make_user(role="admin")
    headers = bearer(await login(client, owner.username))
    incomplete = await client.patch("/api/auth/me/profile", json={"email": ""}, headers=headers)
    assert incomplete.status_code == 422
    response = await client.patch(
        "/api/auth/me/profile",
        json={"full_name": "  " + "n" * 128 + "  ", "email": "  ", "avatar": ""},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["full_name"] == "n" * 128
    assert response.json()["email"] == ""
    page = 1
    while True:
        accounts = await client.get(
            "/api/admin/users", params={"page": page, "page_size": 100}, headers=headers
        )
        assert accounts.status_code == 200, accounts.text
        body = accounts.json()
        listed = next((user for user in body["items"] if user["id"] == owner.id), None)
        if listed is not None:
            break
        assert page * 100 < body["total"], "Profile owner missing from admin user list"
        page += 1
    assert listed == response.json()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "not-an-email"),
        ("email", "name@example..com"),
        ("email", "a b@example.com"),
        ("email", "Name <name@example.com>"),
        ("email", "a" * 245 + "@example.com"),
        ("email", None),
        ("full_name", "n" * 129),
        ("avatar", "data:image/svg+xml;base64,PHN2Zy8+"),
        ("avatar", "data:image/png;base64,%%%%"),
        ("avatar", "data:image/png;base64," + base64.b64encode(b"not an image").decode()),
        ("avatar", "data:image/jpeg;base64," + avatar().split(",", 1)[1]),
        (
            "avatar",
            "data:image/png;base64,"
            + base64.b64encode(base64.b64decode(avatar().split(",", 1)[1])[:40]).decode(),
        ),
        ("avatar", "data:image/png;base64," + base64.b64encode(b"x" * (256 * 1024 + 1)).decode()),
        ("avatar", None),
        ("id", "user:someone_else"),
        ("username", "replacement"),
        ("role", "admin"),
    ],
)
async def test_profile_rejects_invalid_or_immutable_fields(
    client: AsyncClient, make_user: UserFactory, field: str, value: object
) -> None:
    owner = await make_user()
    headers = bearer(await login(client, owner.username))
    response = await client.patch(
        "/api/auth/me/profile",
        json={"full_name": "", "email": "", "avatar": "", field: value},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert (await client.get("/api/auth/me", headers=headers)).json() == owner.model_dump(
        exclude={"password_hash"}
    )
