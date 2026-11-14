from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.auth import find_user
from app.db.client import get_db
from app.db.migrate import MIGRATIONS, discover, run_migrations
from app.db.migration_test_support import history, probe_value, tables
from app.db.test_support import database_names, isolated_database, write_probe
from app.db.test_support import test_database_settings as database_settings
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_session_is_migrated_once(
    db: AsyncWsSurrealConnection, session_db: AsyncWsSurrealConnection
) -> None:
    assert db is session_db
    before = await history(db)
    assert len(before) == len(discover(MIGRATIONS))
    assert await run_migrations(db) == []
    assert await history(db) == before


@pytest.mark.fresh_db
async def test_marker_gets_empty_independent_database(
    db: AsyncWsSurrealConnection,
    session_db: AsyncWsSurrealConnection,
    test_settings: Settings,
    session_db_settings: Settings,
) -> None:
    assert db is not session_db
    assert test_settings.surreal_database != session_db_settings.surreal_database
    assert await tables(db) == {}
    await write_probe(db, test_settings.surreal_database)
    assert await probe_value(db) == test_settings.surreal_database
    assert await history(session_db)


@pytest.mark.fresh_db
async def test_second_marked_test_is_also_empty(db: AsyncWsSurrealConnection) -> None:
    assert await tables(db) == {}


async def test_client_uses_test_database_and_real_lifespan(
    db: AsyncWsSurrealConnection,
    app: FastAPI,
    client: AsyncClient,
    test_settings: Settings,
) -> None:
    await write_probe(db, test_settings.surreal_database)

    @app.get("/api/harness-probe")
    async def probe(connection: Annotated[Any, Depends(get_db)]) -> dict[str, str]:
        return {"value": await probe_value(connection)}

    assert app.state.database.settings is test_settings
    assert (await client.get("/api/readyz")).status_code == 200
    response = await client.get("/api/harness-probe")
    assert response.json() == {"value": test_settings.surreal_database}


async def test_cleanup_removes_only_owned_database_even_on_failure() -> None:
    survivor = database_settings()
    removed = database_settings()
    async with isolated_database(survivor, migrate=True) as other:
        await write_probe(other, survivor.surreal_database)
        with pytest.raises(RuntimeError, match="intentional"):
            async with isolated_database(removed, migrate=True):
                raise RuntimeError("intentional")
        assert removed.surreal_database not in await database_names(other)
        assert survivor.surreal_database in await database_names(other)
        # Reopening the exact name must reveal an empty DB, not a leftover schema.
        async with isolated_database(removed, migrate=False) as reopened:
            assert await tables(reopened) == {}
        assert await probe_value(other) == survivor.surreal_database
        assert await history(other)


async def test_user_factory_persists_fresh_owners(
    db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    first, second = await make_user(), await make_user()
    assert first.id != second.id
    assert await find_user(db, first.id) == first
    assert await find_user(db, second.id) == second
