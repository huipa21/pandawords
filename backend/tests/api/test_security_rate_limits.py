import pytest
from httpx import ASGITransport, AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db import images as image_repository
from app.main import create_app
from app.services.login_backoff import LoginBackoff
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_real_auth_and_user_limits_ignore_untrusted_forwarding_and_expire(
    test_settings: Settings, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user()
    settings = test_settings.model_copy(
        update={"rate_limit_auth": 2, "rate_limit_user": 2, "rate_limit_anonymous": 20}
    )
    app = create_app(settings)
    now = [0.0]
    app.state.rate_limits.clock = lambda: now[0]
    async with app.router.lifespan_context(app):
        async with (
            AsyncClient(
                transport=ASGITransport(app=app, client=("192.0.2.1", 1)),
                base_url="http://test",
            ) as first,
            AsyncClient(
                transport=ASGITransport(app=app, client=("192.0.2.2", 1)),
                base_url="http://test",
            ) as second,
        ):
            ah = bearer(await login(first, alice.username))
            bh = bearer(await login(first, bob.username))
            blocked = await first.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": "203.0.113.8"},
                json={"username": "different", "password": "synthetic-password"},
            )
            assert blocked.status_code == 429
            assert blocked.json()["code"] == "http.too_many_requests"
            assert blocked.headers["retry-after"] == "60"
            assert blocked.headers["cache-control"] == "no-store"
            assert "x-request-id" in blocked.headers
            assert "set-cookie" not in blocked.headers
            for forwarded in ("203.0.113.10", "203.0.113.11"):
                assert (
                    await first.get("/api/auth/me", headers={**ah, "X-Forwarded-For": forwarded})
                ).status_code == 200
            assert (await second.get("/api/auth/me", headers=ah)).status_code == 429
            assert (await first.get("/api/auth/me", headers=bh)).status_code == 200
            now[0] = 59.1
            assert (await second.get("/api/auth/me", headers=ah)).headers["retry-after"] == "1"
            now[0] = 60.0
            assert (await second.get("/api/auth/me", headers=ah)).status_code == 200
            assert (await login(first, alice.username)).status_code == 200


async def test_real_login_backoff_uses_only_explicitly_trusted_proxy_address(
    test_settings: Settings, make_user: UserFactory
) -> None:
    owner = await make_user()
    settings = test_settings.model_copy(
        update={"trusted_proxy_cidrs": ["192.0.2.1/32"], "rate_limit_auth": 20}
    )
    app = create_app(settings)
    app.state.login_backoff = LoginBackoff(clock=lambda: 0.0)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("192.0.2.1", 1)), base_url="http://test"
        ) as client:
            body = {"username": owner.username, "password": "synthetic-wrong-password"}
            first = await client.post(
                "/api/auth/login", headers={"X-Forwarded-For": "203.0.113.10"}, json=body
            )
            assert first.status_code == 401
            blocked = await client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": "203.0.113.10", "X-Real-IP": "203.0.113.99"},
                json=body,
            )
            assert blocked.status_code == 429
            assert blocked.json()["code"] == "auth.login_throttled"
            assert blocked.headers["retry-after"] == "1"
            independent = await client.post(
                "/api/auth/login", headers={"X-Forwarded-For": "203.0.113.11"}, json=body
            )
            assert independent.status_code == 401


async def test_image_provider_cooldown_returns_standard_retry_guidance(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    test_settings: Settings,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await make_user()
    headers = bearer(await login(client, owner.username))
    monkeypatch.setattr(test_settings, "pixabay_api_key", "synthetic-provider-key")
    await image_repository.cooldown(db, owner.id, 17)
    response = await client.get("/api/images/pixabay/search?q=cat", headers=headers)
    assert response.status_code == 429
    assert response.json() == {
        "code": "image.rate_limit",
        "message": "Please wait before another provider request.",
        "field": None,
    }
    assert 1 <= int(response.headers["retry-after"]) <= 17
    assert response.headers["cache-control"] == "no-store"
