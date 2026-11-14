from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.services.login_backoff import LoginBackoff
from tests.api.auth_support import PASSWORD, assert_invalid, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


@dataclass
class Clock:
    now: float = 100.0

    def __call__(self) -> float:
        return self.now


def assert_throttled(response: Response) -> None:
    assert response.status_code == 429
    assert response.json() == {
        "code": "auth.login_throttled",
        "message": "Invalid credentials.",
        "field": None,
    }
    assert "set-cookie" not in response.headers


async def test_exponential_backoff_and_success_reset_without_sleep(
    app: FastAPI, client: AsyncClient, make_user: UserFactory
) -> None:
    clock = Clock()
    app.state.login_backoff = LoginBackoff(clock=clock)
    owner = await make_user()
    for delay in (1, 2, 4, 8, 16, 32, 60, 60):
        assert_invalid(await login(client, owner.username, "incorrect-password"))
        clock.now += delay - 0.01
        assert_throttled(await login(client, owner.username))
        clock.now += 0.01
    assert (await login(client, owner.username)).status_code == 200
    # Immediate failure after success is admitted; its delay restarts at one second.
    assert_invalid(await login(client, owner.username, "incorrect-password"))
    assert_throttled(await login(client, owner.username))
    clock.now += 1
    assert (await login(client, owner.username)).status_code == 200


async def test_backoff_keys_username_and_transport_ip_not_forwarded_headers(
    app: FastAPI, make_user: UserFactory
) -> None:
    app.state.login_backoff = LoginBackoff(clock=Clock())
    owner, other = await make_user(), await make_user()
    async with (
        AsyncClient(
            transport=ASGITransport(app=app, client=("192.0.2.1", 1000)), base_url="http://test"
        ) as first,
        AsyncClient(
            transport=ASGITransport(app=app, client=("192.0.2.2", 1000)), base_url="http://test"
        ) as second,
    ):
        assert_invalid(await login(first, owner.username, "incorrect-password"))
        assert_throttled(await login(first, owner.username))
        spoofed = await first.post(
            "/api/auth/login",
            json={"username": owner.username, "password": PASSWORD},
            headers={"X-Forwarded-For": "192.0.2.3", "Forwarded": "for=192.0.2.3"},
        )
        assert_throttled(spoofed)
        assert (await login(first, other.username)).status_code == 200
        assert (await login(second, owner.username)).status_code == 200
        assert_throttled(await login(first, owner.username))


async def test_unknown_and_disabled_accounts_cannot_bypass_backoff(
    app: FastAPI, client: AsyncClient, make_user: UserFactory
) -> None:
    clock = Clock()
    app.state.login_backoff = LoginBackoff(clock=clock, ttl=900)
    disabled = await make_user(disabled=True)
    for username in (f"missing_{disabled.username}", disabled.username):
        assert_invalid(await login(client, username))
        assert_throttled(await login(client, username))
    clock.now += 900
    for username in (f"missing_{disabled.username}", disabled.username):
        assert_invalid(await login(client, username))
