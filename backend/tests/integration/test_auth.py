import asyncio
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
import structlog
from httpx import ASGITransport, AsyncClient
from surrealdb import AsyncSurrealConnection
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import decode_access_token, hash_refresh_token, verify_password
from app.db.auth import _rows, find_by_username
from app.db.auth_test_support import (
    admins,
    disable_user,
    expire_token,
    is_bootstrap_lookup,
    is_refresh_lookup,
    tokens_for,
)
from app.db.client import DatabaseClient
from app.domain.auth import AuthTokens
from app.main import create_app
from app.services.auth import bootstrap_admin, login, logout, refresh
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
PASSWORD = "test-password-123"


async def test_login_factory_and_generic_failures(
    db: AsyncWsSurrealConnection, test_settings: Settings, make_user: UserFactory
) -> None:
    first, second = await make_user(), await make_user()
    assert first.id != second.id
    assert first.username != second.username
    assert first.password_hash != second.password_hash
    with structlog.testing.capture_logs() as logs:
        pair = await login(db, test_settings, first.username, PASSWORD)
        assert decode_access_token(pair.access_token, test_settings).sub == first.id
        rows = await tokens_for(db, first.id)
        assert len(rows) == 1
        assert rows[0]["token_hash"] == hash_refresh_token(pair.refresh_token)
        assert pair.refresh_token not in str(rows)
        disabled = await make_user(disabled=True)
        for username, password in [
            (first.username, "incorrect-password"),
            ("missing-user", PASSWORD),
            (disabled.username, PASSWORD),
        ]:
            with pytest.raises(AppError) as error:
                await login(db, test_settings, username, password)
            assert (error.value.code, error.value.status, error.value.message) == (
                "auth.invalid_credentials",
                401,
                "Invalid credentials.",
            )
    assert PASSWORD not in str(logs)
    assert pair.refresh_token not in str(logs)
    assert pair.access_token not in str(logs)


async def test_rotation_and_reuse_revoke_entire_chain_only(
    db: AsyncWsSurrealConnection, test_settings: Settings, make_user: UserFactory
) -> None:
    owner, other = await make_user(), await make_user()
    first = await login(db, test_settings, owner.username, PASSWORD)
    independent = await login(db, test_settings, owner.username, PASSWORD)
    other_session = await login(db, test_settings, other.username, PASSWORD)
    second = await refresh(db, test_settings, first.refresh_token)
    third = await refresh(db, test_settings, second.refresh_token)
    fourth = await refresh(db, test_settings, third.refresh_token)
    assert (
        len({first.refresh_token, second.refresh_token, third.refresh_token, fourth.refresh_token})
        == 4
    )
    with pytest.raises(AppError):
        await refresh(db, test_settings, second.refresh_token)
    rows = await tokens_for(db, owner.id)
    unrelated_hash = hash_refresh_token(independent.refresh_token)
    assert all(row.get("revoked_at") for row in rows if row["token_hash"] != unrelated_hash)
    with pytest.raises(AppError):
        await refresh(db, test_settings, fourth.refresh_token)
    await refresh(db, test_settings, independent.refresh_token)
    await refresh(db, test_settings, other_session.refresh_token)


async def test_concurrent_reuse_revokes_winning_replacement(
    db: AsyncWsSurrealConnection, test_settings: Settings, make_user: UserFactory
) -> None:
    owner = await make_user()
    first = await login(db, test_settings, owner.username, PASSWORD)
    lookups = 0
    both_read = asyncio.Event()

    async def synchronized_rows(
        connection: AsyncSurrealConnection,
        query: str,
        variables: dict[str, Value],
        *,
        txn_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        nonlocal lookups
        rows = await _rows(connection, query, variables, txn_id=txn_id)
        if is_refresh_lookup(query):
            lookups += 1
            if lookups <= 2:
                if lookups == 2:
                    both_read.set()
                await asyncio.wait_for(both_read.wait(), timeout=5)
        return rows

    # Independent connections exercise server transaction conflicts, not an in-process lock.
    async with AsyncWsSurrealConnection(test_settings.surreal_url) as other:
        await other.signin(
            {"username": test_settings.surreal_user, "password": test_settings.surreal_pass}
        )
        await other.use(test_settings.surreal_namespace, test_settings.surreal_database)
        with patch("app.db.auth._rows", side_effect=synchronized_rows):
            results = await asyncio.gather(
                refresh(db, test_settings, first.refresh_token),
                refresh(other, test_settings, first.refresh_token),
                return_exceptions=True,
            )
    winners = [result for result in results if isinstance(result, AuthTokens)]
    failures = [result for result in results if isinstance(result, AppError)]
    assert len(winners) == len(failures) == 1, [type(result).__name__ for result in results]
    assert lookups >= 3  # Both initial snapshots read the active token; the loser retried.
    assert failures[0].code == "auth.invalid_credentials"
    assert all(row.get("revoked_at") for row in await tokens_for(db, owner.id))
    with pytest.raises(AppError):
        await refresh(db, test_settings, winners[0].refresh_token)


async def test_logout_expiry_and_disabled_accounts(
    db: AsyncWsSurrealConnection, test_settings: Settings, make_user: UserFactory
) -> None:
    owner, other = await make_user(), await make_user()
    unrelated = await login(db, test_settings, other.username, PASSWORD)
    pair = await login(db, test_settings, owner.username, PASSWORD)
    rotated = await refresh(db, test_settings, pair.refresh_token)
    await logout(db, pair.refresh_token)
    await logout(db, pair.refresh_token)
    with pytest.raises(AppError):
        await refresh(db, test_settings, rotated.refresh_token)
    expired = await login(db, test_settings, owner.username, PASSWORD)
    await expire_token(db, owner.id, hash_refresh_token(expired.refresh_token))
    with pytest.raises(AppError):
        await refresh(db, test_settings, expired.refresh_token)
    disabled = await login(db, test_settings, owner.username, PASSWORD)
    await disable_user(db, owner.id)
    with pytest.raises(AppError):
        await refresh(db, test_settings, disabled.refresh_token)
    await refresh(db, test_settings, unrelated.refresh_token)


@pytest.mark.fresh_db
async def test_bootstrap_exactly_once_and_production_forced_change(
    db: AsyncWsSurrealConnection, test_settings: Settings
) -> None:
    from app.db.migrate import run_migrations

    await run_migrations(db)
    settings = test_settings.model_copy(update={"app_env": "production"})
    first_app = create_app(settings)
    async with first_app.router.lifespan_context(first_app):
        first = await find_by_username(db, settings.admin_username)
    assert first is not None
    assert first.role == "admin" and first.must_change_password
    assert verify_password(settings.admin_password, first.password_hash)
    changed = settings.model_copy(update={"admin_password": "different-password-123"})
    second_app = create_app(changed)
    async with second_app.router.lifespan_context(second_app):
        second = await find_by_username(db, settings.admin_username)
    assert second == first
    assert len(await admins(db)) == 1


@pytest.mark.fresh_db
async def test_concurrent_bootstrap_creates_one_admin(
    db: AsyncWsSurrealConnection, test_settings: Settings
) -> None:
    from app.db.migrate import run_migrations

    await run_migrations(db)
    lookups = 0
    both_read = asyncio.Event()

    async def synchronized_rows(
        connection: AsyncSurrealConnection,
        query: str,
        variables: dict[str, Value],
        *,
        txn_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        nonlocal lookups
        rows = await _rows(connection, query, variables, txn_id=txn_id)
        if txn_id is not None and is_bootstrap_lookup(query):
            lookups += 1
            if lookups <= 2:
                assert not rows
                if lookups == 2:
                    both_read.set()
                await asyncio.wait_for(both_read.wait(), timeout=5)
        return rows

    async with AsyncWsSurrealConnection(test_settings.surreal_url) as other:
        await other.signin(
            {"username": test_settings.surreal_user, "password": test_settings.surreal_pass}
        )
        await other.use(test_settings.surreal_namespace, test_settings.surreal_database)
        with patch("app.db.auth._rows", side_effect=synchronized_rows):
            await asyncio.gather(
                bootstrap_admin(db, test_settings), bootstrap_admin(other, test_settings)
            )
    rows = await admins(db)
    assert len(rows) == 1
    assert lookups >= 3
    assert verify_password(test_settings.admin_password, rows[0]["password_hash"])


@pytest.mark.fresh_db
async def test_bootstrap_failure_aborts_startup_without_secrets(
    db: AsyncWsSurrealConnection, test_settings: Settings
) -> None:
    from app.db.migrate import run_migrations

    await run_migrations(db)
    settings = test_settings.model_copy(update={"admin_password": ""})
    app = create_app(settings)
    with pytest.raises(ValueError, match="Initial admin credentials"):
        async with app.router.lifespan_context(app):
            pytest.fail("Invalid bootstrap must not silently succeed")
    assert not await admins(db)


async def test_slow_bootstrap_preserves_health_then_opens_readiness(
    db: AsyncWsSurrealConnection, test_settings: Settings
) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_bootstrap(connection: AsyncSurrealConnection, settings: Settings) -> None:
        started.set()
        await release.wait()
        await bootstrap_admin(connection, settings)

    settings = test_settings.model_copy(update={"surreal_timeout_seconds": 0.1})
    application = create_app(settings)
    database = DatabaseClient(test_settings)
    with (
        patch("app.main.bootstrap_admin", side_effect=delayed_bootstrap),
        patch("app.db.client.DatabaseClient", return_value=database),
    ):
        async with asyncio.timeout(5):
            async with application.router.lifespan_context(application):
                await started.wait()
                async with AsyncClient(
                    transport=ASGITransport(app=application), base_url="http://test"
                ) as client:
                    assert (await client.get("/api/healthz")).status_code == 200
                    assert (await client.get("/api/openapi.json")).status_code == 200
                    response = await client.get("/api/readyz")
                    assert response.status_code == 503
                    assert response.json()["code"] == "auth.unavailable"
                    release.set()
                    await application.state.auth_initialization
                    assert (await client.get("/api/readyz")).status_code == 200


@pytest.mark.fresh_db
async def test_late_bootstrap_failure_keeps_readiness_closed(
    db: AsyncWsSurrealConnection, test_settings: Settings
) -> None:
    from app.db.migrate import run_migrations

    await run_migrations(db)
    allow_connection = asyncio.Event()
    connect = DatabaseClient.connect

    async def delayed_connect(database: DatabaseClient) -> None:
        await allow_connection.wait()
        await connect(database)

    settings = test_settings.model_copy(
        update={"admin_password": "", "surreal_timeout_seconds": 0.1}
    )
    application = create_app(settings)
    database = DatabaseClient(test_settings)
    with (
        patch.object(DatabaseClient, "connect", delayed_connect),
        patch("app.db.client.DatabaseClient", return_value=database),
    ):
        async with application.router.lifespan_context(application):
            async with AsyncClient(
                transport=ASGITransport(app=application), base_url="http://test"
            ) as client:
                assert (await client.get("/api/healthz")).status_code == 200
                assert (await client.get("/api/readyz")).status_code == 503
                allow_connection.set()
                task = application.state.auth_initialization
                await asyncio.wait([task], timeout=5)
                assert task.done() and isinstance(task.exception(), ValueError)
                response = await client.get("/api/readyz")
                assert response.status_code == 503
                assert response.json()["code"] == "auth.unavailable"
                assert (await client.get("/api/healthz")).status_code == 200
