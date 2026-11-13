import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import structlog
from fastapi import FastAPI
from pydantic_settings import SettingsConfigDict
from starlette.requests import Request

from app.core.config import Settings
from app.core.errors import AppError
from app.db.client import check_database, database_lifespan, get_db
from app.main import create_app


class _TestSettings(Settings):
    model_config = SettingsConfigDict(env_file=None)


async def test_initial_connection_retries_and_closes_without_logging_secrets() -> None:
    connection = AsyncMock()
    connection.connect.side_effect = [OSError("sensitive-password"), None]
    settings = _TestSettings(surreal_pass="sensitive-password")
    with (
        patch("app.db.client.AsyncSurreal", return_value=connection),
        patch("app.db.client.ReconnectOptions.delay", return_value=0),
        structlog.testing.capture_logs() as logs,
    ):
        async with database_lifespan(settings) as database:
            assert await database.get_connection() is connection
            connection.signin.assert_awaited_once_with(
                {"username": settings.surreal_user, "password": settings.surreal_pass}
            )
            connection.use.assert_awaited_once_with(
                settings.surreal_namespace, settings.surreal_database
            )
            assert connection.connect.await_count == 2
        assert connection.close.await_count == 2

    assert "sensitive-password" not in str(logs)
    assert any(log["event"] == "database_connect_failed" for log in logs)


async def test_shutdown_cancels_pending_connect() -> None:
    connection = AsyncMock()
    connecting = asyncio.Event()

    async def hang() -> None:
        connecting.set()
        await asyncio.Event().wait()

    connection.connect.side_effect = hang
    with patch("app.db.client.AsyncSurreal", return_value=connection):
        async with database_lifespan(_TestSettings()):
            await connecting.wait()
        connection.close.assert_awaited_once()


@pytest.mark.parametrize("failure", [OSError("secret"), TimeoutError()])
async def test_readiness_failure_is_safe_and_does_not_replace_connection(
    failure: Exception,
) -> None:
    connection = AsyncMock()
    connection.query.side_effect = failure
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(AppError) as error:
            await check_database(connection, 0.1)
    assert error.value.status == 503
    assert "secret" not in str(logs)


@pytest.mark.parametrize("result", [[], [{"status": "ERR", "result": "Unavailable"}]])
async def test_readiness_rejects_unsuccessful_statement_results(result: object) -> None:
    connection = AsyncMock()
    connection.query.return_value = result
    with pytest.raises(AppError) as error:
        await check_database(connection, 0.1)
    assert error.value.status == 503


async def test_readiness_has_a_deadline() -> None:
    connection = AsyncMock()

    async def hang(_: str) -> None:
        await asyncio.Event().wait()

    connection.query.side_effect = hang
    with pytest.raises(AppError) as error:
        await check_database(connection, 0.01)
    assert error.value.status == 503


async def test_get_db_dependency_returns_lifespan_connection() -> None:
    connection = AsyncMock()
    with patch("app.db.client.AsyncSurreal", return_value=connection):
        async with database_lifespan(_TestSettings()) as database:
            app = FastAPI()
            app.state.database = database
            request_scope = {"type": "http", "app": app}
            assert await get_db(Request(request_scope)) is connection


def test_openapi_generation_does_not_construct_database_client() -> None:
    with patch("app.db.client.AsyncSurreal", side_effect=AssertionError("No database")):
        assert "/api/readyz" in create_app(_TestSettings()).openapi()["paths"]


def test_non_websocket_database_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="WebSocket"):
        _TestSettings(surreal_url="http://localhost:8101")
