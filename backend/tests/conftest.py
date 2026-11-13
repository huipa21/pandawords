from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.test_support import isolated_database, test_database_settings
from app.main import create_app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def session_db_settings() -> Settings:
    return test_database_settings()


@pytest.fixture(scope="session")
async def session_db(
    anyio_backend: str, session_db_settings: Settings
) -> AsyncIterator[AsyncWsSurrealConnection]:
    """Migrate once per pytest process; remove exactly this database on teardown."""
    async with isolated_database(session_db_settings, migrate=True) as connection:
        yield connection


@pytest.fixture
def test_settings(request: pytest.FixtureRequest, session_db_settings: Settings) -> Settings:
    if request.node.get_closest_marker("fresh_db"):
        return test_database_settings()
    return session_db_settings


@pytest.fixture
async def db(
    request: pytest.FixtureRequest, test_settings: Settings
) -> AsyncIterator[AsyncWsSurrealConnection]:
    """Shared migrated DB, or an empty per-test DB for @pytest.mark.fresh_db."""
    if request.node.get_closest_marker("fresh_db"):
        async with isolated_database(test_settings, migrate=False) as connection:
            yield connection
    else:
        yield request.getfixturevalue("session_db")


@pytest.fixture
async def app(db: AsyncWsSurrealConnection, test_settings: Settings) -> AsyncIterator[FastAPI]:
    """Run the real lifespan with test settings, including startup/shutdown hooks."""
    application = create_app(test_settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def make_user() -> Callable[..., Any]:
    async def factory(**attributes: Any) -> Any:
        raise NotImplementedError(
            "make_user is unfinished until task 1.5.x provides the user schema and auth services; "
            "the factory must create a fresh owner for each call."
        )

    return factory
