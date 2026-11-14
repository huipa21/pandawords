import asyncio
from collections.abc import AsyncIterator
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_settings import SettingsConfigDict
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.client import DatabaseClient
from app.main import create_app


class _TestSettings(Settings):
    model_config = SettingsConfigDict(env_file=None)


@pytest.fixture
async def db(
    session_db: AsyncWsSurrealConnection, test_settings: Settings
) -> AsyncIterator[FastAPI]:
    app = create_app(test_settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.mark.integration
async def test_readyz_queries_database_and_reuses_connection(db: FastAPI) -> None:
    database = cast(DatabaseClient, db.state.database)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=db), base_url="http://test"
    ) as client:
        first = await client.get("/api/readyz")
        connection = await database.get_connection()
        second = await client.get("/api/readyz")

    assert first.status_code == second.status_code == 200
    assert first.json() == {"status": "ok"}
    assert connection is await database.get_connection()


@pytest.mark.integration
async def test_readyz_accepts_legacy_localhost_configuration(
    session_db: AsyncWsSurrealConnection, test_settings: Settings
) -> None:
    settings = Settings.model_validate(
        {**test_settings.model_dump(), "surreal_url": "ws://localhost:8101/rpc"}
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
async def test_sdk_reconnects_the_same_connection_after_socket_loss(db: FastAPI) -> None:
    database = cast(DatabaseClient, db.state.database)
    connection = await database.get_connection()
    assert isinstance(connection, AsyncWsSurrealConnection)
    assert connection.socket is not None
    await connection.socket.close()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=db), base_url="http://test"
    ) as client:
        async with asyncio.timeout(12):
            for _ in range(12):
                if (await client.get("/api/readyz")).status_code == 200:
                    break
                await asyncio.sleep(0.1)
            else:
                pytest.fail("SDK did not reconnect")
    assert await database.get_connection() is connection


def test_unreachable_database_preserves_startup_health_and_openapi() -> None:
    settings = _TestSettings(
        surreal_url="ws://127.0.0.1:1/rpc",
        surreal_timeout_seconds=0.1,
        surreal_pass="must-not-appear-in-responses",
        jwt_secret="readiness-test-secret-at-least-32-bytes",
        admin_username="readiness_admin",
        admin_password="test-admin-password-123",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/healthz").status_code == 200
        response = client.get("/api/readyz")
        assert client.get("/api/openapi.json").status_code == 200

    assert response.status_code == 503
    assert response.json() == {
        "code": "database.unavailable",
        "message": "Database is unavailable.",
        "field": None,
    }


@pytest.mark.integration
async def test_invalid_credentials_do_not_make_database_ready(test_settings: Settings) -> None:
    settings = test_settings
    app = create_app(
        settings.model_copy(
            update={
                "surreal_url": settings.surreal_test_url,
                "surreal_pass": "invalid-test-password",
                "surreal_timeout_seconds": 0.3,
            }
        )
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/readyz")).status_code == 503
            assert (await client.get("/api/healthz")).status_code == 200
