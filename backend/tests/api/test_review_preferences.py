import pytest
from httpx import AsyncClient

from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
URL = "/api/auth/me/review-preferences"
DEFAULTS = {"review_images_enabled": True, "review_audio_enabled": True, "accent": "US"}


async def test_partial_persistent_owner_scoped_preferences(
    client: AsyncClient, make_user: UserFactory
) -> None:
    user, other = await make_user(), await make_user()
    headers = bearer(await login(client, user.username))
    foreign = bearer(await login(client, other.username))
    response = await client.get(URL, headers=headers)
    assert response.status_code == 200 and response.json() == DEFAULTS
    assert response.headers["cache-control"] == "no-store"
    await client.patch(
        "/api/auth/me/srs-preferences", headers=headers, json={"desired_retention": 0.97}
    )
    expected = dict(DEFAULTS)
    for data in (
        {"review_images_enabled": False},
        {"review_audio_enabled": False},
        {"accent": "UK"},
        {"review_images_enabled": True},
        {"review_audio_enabled": True},
        {"accent": "US"},
    ):
        expected.update(data)
        updated = await client.patch(f"{URL}?owner={other.id}", headers=headers, json=data)
        assert updated.status_code == 200, updated.text
        assert updated.json() == expected
        assert (await client.get(URL, headers=headers)).json() == expected
        assert (await client.get(f"{URL}?owner={user.id}", headers=foreign)).json() == DEFAULTS
        me = (await client.get("/api/auth/me", headers=headers)).json()
        assert me["prefs"] == {**user.prefs.model_dump(), "desired_retention": 0.97, **expected}
    assert (await client.get(URL)).status_code == 401
    assert (await client.patch(URL, json={"accent": "UK"})).status_code == 401


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"accent": "AU"},
        {"accent": None},
        {"review_images_enabled": None},
        {"review_images_enabled": "false"},
        {"review_audio_enabled": 0},
        {"review_audio_enabled": "true"},
        {"theme": "dark"},
        {"owner": "user:other"},
    ],
)
async def test_invalid_partial_preferences_do_not_mutate(
    client: AsyncClient, make_user: UserFactory, data: dict
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    response = await client.patch(URL, headers=headers, json=data)
    assert response.status_code == 422, response.text
    assert (await client.get(URL, headers=headers)).json() == DEFAULTS
