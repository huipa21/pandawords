import pytest
from httpx import AsyncClient

from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
URL = "/api/auth/me/srs-preferences"


async def test_retention_settings_are_owner_scoped_and_preserve_other_preferences(
    client: AsyncClient,
    make_user: UserFactory,
) -> None:
    user, other = await make_user(), await make_user()
    headers = bearer(await login(client, user.username))
    other_headers = bearer(await login(client, other.username))
    initial = await client.get(URL, headers=headers)
    assert initial.json() == {"desired_retention": 0.9}
    assert initial.headers["cache-control"] == "no-store"
    updated = await client.patch(
        f"{URL}?user_id={other.id}",
        headers=headers,
        json={"desired_retention": 0.97},
    )
    assert updated.status_code == 200 and updated.json() == {"desired_retention": 0.97}
    foreign = await client.get(f"{URL}?user_id={user.id}", headers=other_headers)
    assert foreign.json() == {"desired_retention": 0.9}
    await client.patch(
        f"{URL}?user_id={user.id}",
        headers=other_headers,
        json={"desired_retention": 0.8},
    )
    assert (await client.get(URL, headers=headers)).json() == {"desired_retention": 0.97}
    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["prefs"] == {**user.prefs.model_dump(), "desired_retention": 0.97}
    assert (await client.get(URL)).status_code == 401


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"desired_retention": 0},
        {"desired_retention": 1},
        {"desired_retention": None},
        {"desired_retention": -1},
        {"desired_retention": 0.9, "owner": "user:other"},
    ],
)
async def test_invalid_retention_rejected(
    client: AsyncClient,
    make_user: UserFactory,
    data: dict,
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    response = await client.patch(URL, headers=headers, json=data)
    assert response.status_code == 422
    assert (await client.get(URL, headers=headers)).json() == {"desired_retention": 0.9}
