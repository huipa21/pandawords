from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.test_support import isolated_database, test_database_settings
from app.domain.auth import Role, User, UserCreate
from app.main import create_app
from app.services.auth import create_user
from app.services.lexicon import LexiconReader

pytest_plugins = ["tests.snapshot_plugin"]


@pytest.fixture
def lexicon_reader() -> LexiconReader:
    return LexiconReader(Path(__file__).parent / "fixtures" / "lexicon_small.sqlite")


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
def job_settings() -> Settings:
    return test_database_settings()


@pytest.fixture
async def job_db(job_settings: Settings) -> AsyncIterator[AsyncWsSurrealConnection]:
    async with isolated_database(job_settings, migrate=True) as connection:
        yield connection


@pytest.fixture
async def db(
    request: pytest.FixtureRequest,
    test_settings: Settings,
    session_db: AsyncWsSurrealConnection,
) -> AsyncIterator[AsyncWsSurrealConnection]:
    """Shared migrated DB, or an empty per-test DB for @pytest.mark.fresh_db."""
    if request.node.get_closest_marker("fresh_db"):
        async with isolated_database(test_settings, migrate=False) as connection:
            yield connection
    else:
        yield session_db


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


class UserFactory(Protocol):
    async def __call__(
        self,
        *,
        username: str | None = None,
        password: str = "test-password-123",
        role: Role = "user",
        disabled: bool = False,
        must_change_password: bool = False,
    ) -> User: ...


@pytest.fixture
def make_user(db: AsyncWsSurrealConnection) -> UserFactory:
    async def factory(
        *,
        username: str | None = None,
        password: str = "test-password-123",
        role: Role = "user",
        disabled: bool = False,
        must_change_password: bool = False,
    ) -> User:
        return await create_user(
            db,
            UserCreate(
                username=username if username is not None else f"user_{uuid4().hex}",
                password=password,
                role=role,
                disabled=disabled,
                must_change_password=must_change_password,
            ),
        )

    return factory
