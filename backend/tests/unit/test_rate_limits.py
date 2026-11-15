from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.config import Settings
from app.core.errors import AppError
from app.core.rate_limits import RateLimitMiddleware, RateLimits
from app.core.security import create_access_token
from app.domain.identity import user_subject
from app.services.login_backoff import LoginBackoff


class TestSettings(Settings):
    __test__ = False
    model_config = SettingsConfigDict(env_file=None)


def settings(**overrides: object) -> Settings:
    return TestSettings(jwt_secret="test-only-secret-for-rate-limit-tests").model_copy(
        update=overrides
    )


async def echo(request: Request) -> JSONResponse:
    return JSONResponse({"peer": request.client.host if request.client else None})


async def scheme(request: Request) -> JSONResponse:
    return JSONResponse({"scheme": request.url.scheme})


async def transport_client(
    config: Settings, limits: RateLimits, peer: str = "192.0.2.1"
) -> AsyncIterator[AsyncClient]:
    application = Starlette(
        routes=[
            Route("/api/scheme", scheme),
            Route("/{path:path}", echo, methods=["GET", "POST"]),
        ]
    )
    application.add_middleware(RateLimitMiddleware, settings=config, limits=limits)
    async with AsyncClient(
        transport=ASGITransport(app=application, client=(peer, 1234)),
        base_url="http://test",
    ) as client:
        yield client


def test_boundary_expiry_and_capacity_fail_closed() -> None:
    now = [0.0]
    limits = RateLimits(settings(rate_limit_capacity=1), clock=lambda: now[0])
    limits.admit("api", "alice", 2)
    limits.admit("api", "alice", 2)
    for identity in ("alice", "bob"):
        with pytest.raises(AppError) as exc:
            limits.admit("api", identity, 2)
        assert exc.value.status == 429
        assert exc.value.headers == {"Retry-After": "60", "Cache-Control": "no-store"}
    assert len(limits.windows) == 1
    now[0] = 60
    limits.admit("api", "bob", 2)
    assert list(limits.windows) == [("api", "bob")]


def test_login_backoff_capacity_does_not_evict_live_restrictions() -> None:
    now = [0.0]
    backoff = LoginBackoff(clock=lambda: now[0], capacity=1, ttl=20)
    key = backoff.begin("alice", "192.0.2.1")
    backoff.finish(key, success=False)
    with pytest.raises(AppError) as full:
        backoff.begin("bob", "192.0.2.1")
    assert full.value.status == 429
    assert full.value.headers is not None
    assert full.value.headers["Retry-After"] == "20"
    with pytest.raises(AppError) as throttled:
        backoff.begin("alice", "192.0.2.1")
    assert throttled.value.headers is not None
    assert throttled.value.headers["Retry-After"] == "1"
    now[0] = 20
    backoff.finish(backoff.begin("bob", "192.0.2.1"), success=True)


@pytest.mark.anyio
async def test_anonymous_spoofing_and_health_exemption() -> None:
    config = settings(rate_limit_anonymous=2)
    now = [0.0]
    limits = RateLimits(config, clock=lambda: now[0])
    async for client in transport_client(config, limits):
        for i in range(2):
            assert (
                await client.get(
                    "/api/projects",
                    headers={"X-Forwarded-For": f"203.0.113.{i}", "Forwarded": f"for={i}"},
                )
            ).status_code == 200
        rejected = await client.get("/api/projects", headers={"X-Real-IP": "203.0.113.99"})
        assert rejected.status_code == 429
        assert rejected.json() == {
            "code": "http.too_many_requests",
            "message": "Too many requests.",
            "field": None,
        }
        assert rejected.headers["retry-after"] == "60"
        assert (await client.get("/api/readyz")).status_code == 200
        now[0] = 60
        assert (await client.get("/api/projects")).status_code == 200


@pytest.mark.anyio
async def test_verified_user_identity_not_token_or_ip_and_expensive_budget() -> None:
    config = settings(rate_limit_user=2, rate_limit_expensive=1)
    limits = RateLimits(config)
    alice = create_access_token(user_subject("alice"), "user", config)
    bob = create_access_token(user_subject("bob"), "user", config)
    async for client in transport_client(config, limits):
        headers = {"Authorization": f"Bearer {alice}"}
        assert (await client.get("/api/graph/seeds", headers=headers)).status_code == 200
        assert (await client.get("/api/graph/expand", headers=headers)).status_code == 429
        assert (await client.get("/api/projects", headers=headers)).status_code == 429
        assert (
            await client.get("/api/graph/seeds", headers={"Authorization": f"Bearer {bob}"})
        ).status_code == 200
        # A forged token spends only the anonymous budget.
        assert (
            await client.get("/api/projects", headers={"Authorization": "Bearer forged"})
        ).status_code == 200
    async for client in transport_client(config, limits, peer="192.0.2.9"):
        assert (
            await client.get("/api/projects", headers={"Authorization": f"Bearer {alice}"})
        ).status_code == 429


@pytest.mark.anyio
async def test_auth_budget_survives_user_and_username_rotation() -> None:
    config = settings(rate_limit_auth=2)
    limits = RateLimits(config)
    async for client in transport_client(config, limits):
        for name in ("alice", "bob"):
            token = create_access_token(user_subject(name), "user", config)
            assert (
                await client.post(
                    "/api/auth/login",
                    json={"username": name},
                    headers={"Authorization": f"Bearer {token}"},
                )
            ).status_code == 200
        assert (await client.post("/api/auth/refresh")).status_code == 429


@pytest.mark.anyio
async def test_explicit_proxy_only_single_valid_canonical_address() -> None:
    config = settings(trusted_proxy_cidrs=["192.0.2.0/24"], rate_limit_anonymous=1)
    limits = RateLimits(config)
    async for client in transport_client(config, limits):
        for address in ("203.0.113.1", "203.0.113.2"):
            result = await client.get("/api/projects", headers={"X-Forwarded-For": address})
            assert result.json() == {"peer": address}
        result = await client.get(
            "/api/projects", headers={"X-Forwarded-For": "203.0.113.3, 203.0.113.4"}
        )
        assert result.json() == {"peer": "192.0.2.1"}
        assert (
            await client.get("/api/projects", headers={"X-Forwarded-For": "invalid"})
        ).status_code == 429
    for values in (["0.0.0.0/0"], ["::/0"], ["hostname"]):
        with pytest.raises(ValidationError):
            TestSettings(trusted_proxy_cidrs=values)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/api/dictionary/lemmas/example/entry",
        "/api/dictionary/lemma/example/phrases",
        "/api/content/sentence/example/occurrences?assist=true",
        "/api/projects/example/tree",
        "/api/projects/example/study-plan",
        "/api/dashboard",
        "/api/graph/seeds",
        "/api/images/pixabay/search?q=cat",
        "/api/media/example",
        "/api/relations?sense_id=example",
        "/api/tags/assignments?target_table=tag&target_id=example",
    ],
)
async def test_expensive_reads_use_their_own_budget(path: str) -> None:
    config = settings(rate_limit_anonymous=20, rate_limit_expensive=1)
    limits = RateLimits(config)
    async for client in transport_client(config, limits):
        assert (await client.get(path)).status_code == 200
        assert (await client.get(path)).status_code == 429


@pytest.mark.anyio
async def test_forwarded_ipv6_scope_and_mapped_addresses_cannot_split_a_bucket() -> None:
    config = settings(trusted_proxy_cidrs=["192.0.2.0/24"], rate_limit_anonymous=1)
    limits = RateLimits(config)
    async for client in transport_client(config, limits):
        assert (
            await client.get("/api/projects", headers={"X-Forwarded-For": "203.0.113.1"})
        ).status_code == 200
        assert (
            await client.get("/api/projects", headers={"X-Forwarded-For": "::ffff:203.0.113.1"})
        ).status_code == 429
        assert (
            await client.get("/api/projects", headers={"X-Forwarded-For": "fe80::1%spoof-a"})
        ).status_code == 200
        assert (
            await client.get("/api/projects", headers={"X-Forwarded-For": "fe80::1%spoof-b"})
        ).status_code == 429


@pytest.mark.anyio
async def test_only_trusted_proxy_can_set_https_redirect_scheme() -> None:
    config = settings(trusted_proxy_cidrs=["192.0.2.0/24"])
    limits = RateLimits(config)
    async for client in transport_client(config, limits):
        assert (
            await client.get("/api/scheme", headers={"X-Forwarded-Proto": "https"})
        ).json() == {"scheme": "https"}
        for value in ("http,https", "javascript", ""):
            assert (
                await client.get("/api/scheme", headers={"X-Forwarded-Proto": value})
            ).json() == {"scheme": "http"}
        assert (
            await client.get(
                "/api/scheme",
                headers=[("X-Forwarded-Proto", "https"), ("X-Forwarded-Proto", "http")],
            )
        ).json() == {"scheme": "http"}
    async for client in transport_client(config, limits, peer="198.51.100.1"):
        assert (
            await client.get("/api/scheme", headers={"X-Forwarded-Proto": "https"})
        ).json() == {"scheme": "http"}
