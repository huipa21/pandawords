"""Bounded, process-local admission control; production runs one API worker."""

import heapq
import time
from collections.abc import Callable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

import structlog
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import AppError, app_error_handler, retry_headers
from app.core.security import decode_access_token, validate_auth_settings


@dataclass
class _Window:
    count: int
    expires: float


class RateLimits:
    def __init__(self, settings: Settings, clock: Callable[[], float] = time.monotonic) -> None:
        self.settings = settings
        self.clock = clock
        self.windows: dict[tuple[str, str], _Window] = {}
        self.expirations: list[tuple[float, tuple[str, str]]] = []

    def admit(self, category: str, identity: str, limit: int) -> None:
        now = self.clock()
        while self.expirations and self.expirations[0][0] <= now:
            expires, expired_key = heapq.heappop(self.expirations)
            entry = self.windows.get(expired_key)
            if entry is not None and entry.expires == expires:
                del self.windows[expired_key]
        key = (category, identity)
        entry = self.windows.get(key)
        if entry is None:
            # Never evict a live restriction: identity spraying must fail closed.
            if len(self.windows) >= self.settings.rate_limit_capacity:
                retry = self.expirations[0][0] - now
                self._reject(category, retry)
            entry = _Window(0, now + self.settings.rate_limit_window_seconds)
            self.windows[key] = entry
            heapq.heappush(self.expirations, (entry.expires, key))
        if entry.count >= limit:
            self._reject(category, entry.expires - now)
        entry.count += 1

    @staticmethod
    def _reject(category: str, retry: float) -> None:
        structlog.get_logger().info("rate_limit_rejected", category=category)
        raise AppError(
            "http.too_many_requests",
            429,
            "Too many requests.",
            headers=retry_headers(retry),
        )


def _canonical_ip(value: str) -> IPv4Address | IPv6Address | None:
    try:
        address = ip_address(value)
    except ValueError:
        return None
    if isinstance(address, IPv6Address):
        if address.scope_id is not None:
            return None
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped
    return address


_EXPENSIVE_READS = (
    "/api/graph",
    "/api/dictionary",
    "/api/content",
    "/api/images",
    "/api/media",
    "/api/relations",
    "/api/tags/assignments",
)


def _expensive(method: str, path: str) -> bool:
    if method not in {"GET", "HEAD", "OPTIONS"}:
        return True
    path = path.rstrip("/")
    return (
        path == "/api/dashboard"
        or any(path == prefix or path.startswith(prefix + "/") for prefix in _EXPENSIVE_READS)
        or (path.startswith("/api/projects/") and path.endswith(("/tree", "/study-plan")))
    )


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings, limits: RateLimits) -> None:
        self.app = app
        self.settings = settings
        self.limits = limits
        self.proxies = [ip_network(value) for value in settings.trusted_proxy_cidrs]
        try:
            validate_auth_settings(settings)
        except ValueError:
            self.auth_configured = False
        else:
            self.auth_configured = True

    def _trusted_peer(self, request: Request) -> bool:
        peer = _canonical_ip(request.client.host) if request.client else None
        return peer is not None and any(peer in network for network in self.proxies)

    def _address(self, request: Request) -> str:
        peer = request.client.host if request.client else "unknown"
        address = _canonical_ip(peer)
        if address is None:
            return "unknown"
        if self._trusted_peer(request):
            # Exactly one canonical IP, set by the immediate trusted proxy. Chains,
            # malformed/duplicate headers and other forwarding headers are ignored.
            forwarded = request.headers.getlist("x-forwarded-for")
            if len(forwarded) == 1:
                client = _canonical_ip(forwarded[0])
                if client is not None:
                    return str(client)
        return str(address)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        path = request.url.path
        if not (path == "/api" or path.startswith("/api/")) or path in {
            "/api/healthz",
            "/api/readyz",
        }:
            await self.app(scope, receive, send)
            return
        if self._trusted_peer(request):
            schemes = request.headers.getlist("x-forwarded-proto")
            if len(schemes) == 1 and schemes[0] in {"http", "https"}:
                scope["scheme"] = schemes[0]
        address = self._address(request)
        # Also supplies the existing username/IP login backoff with the safe identity.
        scope["client"] = (address, request.client.port if request.client else 0)
        try:
            if path in {"/api/auth/login", "/api/auth/refresh", "/api/auth/password"}:
                self.limits.admit("auth", address, self.settings.rate_limit_auth)
            identity = "ip:" + address
            limit = self.settings.rate_limit_anonymous
            authorization = request.headers.get("authorization", "").split()
            if authorization and not self.auth_configured:
                structlog.get_logger().warning("rate_limit_token_identity_unavailable")
            if (
                self.auth_configured
                and len(authorization) == 2
                and authorization[0].lower() == "bearer"
            ):
                try:
                    claims = decode_access_token(authorization[1], self.settings)
                except AppError:
                    pass
                else:
                    identity = "user:" + claims.sub
                    limit = self.settings.rate_limit_user
            # Login/refresh always spend the anonymous budget too: presenting a
            # signed token cannot bypass credential-operation address restrictions.
            if path in {"/api/auth/login", "/api/auth/refresh"}:
                identity, limit = "ip:" + address, self.settings.rate_limit_anonymous
            self.limits.admit("api", identity, limit)
            if _expensive(request.method, path):
                self.limits.admit("expensive", identity, self.settings.rate_limit_expensive)
        except AppError as exc:
            response = await app_error_handler(request, exc)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
