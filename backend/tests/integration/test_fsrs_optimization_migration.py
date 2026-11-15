import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fsrs.scheduler import DEFAULT_PARAMETERS
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db import srs_optimization as repository
from app.db.auth import find_user
from app.db.dictionary_schema_test_support import table_info
from app.db.memory_schema_test_support import owned
from app.db.migrate import MIGRATIONS, discover, run_migrations
from app.db.migration_store import MigrationError, checked_query
from app.db.snapshot import snapshot
from app.db.srs import user_record
from app.db.srs_optimization_test_support import history_plans, insert_foreign_identity, seed, set_preferences
from app.domain.auth import UserPreferences
from app.domain.srs_optimization import OptimizationRead
from app.services.srs_optimization_history import training_history
from tests.conftest import UserFactory
from tests.srs_optimization_support import history

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]


def index_scan(plan: dict[str, Any], index: str) -> dict[str, Any] | None:
    if plan.get("operator") == "IndexScan" and plan.get("attributes", {}).get("index") == index:
        return plan
    for child in plan.get("children", []):
        found = index_scan(child, index)
        if found is not None:
            return found
    return None


@pytest.fixture
def prior_migrations() -> Iterator[Path]:
    directory = Path(__file__).resolve().parents[2] / f".fsrs-migration-{uuid4().hex}"
    directory.mkdir()
    try:
        for migration in discover(MIGRATIONS):
            if migration.version < "0024":
                shutil.copyfile(migration.path, directory / migration.path.name)
        yield directory
    finally:
        shutil.rmtree(directory)


async def test_upgrade_and_replay_preserve_history_preferences_and_parameters(
    db: AsyncWsSurrealConnection, make_user: UserFactory, prior_migrations: Path
) -> None:
    await run_migrations(db, prior_migrations)
    user = await make_user()
    prefs = UserPreferences(theme="dark", locale="en", accent="UK", desired_retention=0.97)
    await set_preferences(db, user.id, prefs)
    await seed(db, history(user.id, cards=2, reviews=3))
    cards = await owned(db, "memory", user_record(user.id))
    logs = await owned(db, "review_log", user_record(user.id))
    migration = MIGRATIONS / "0024_srs_optimization.surql"
    shutil.copyfile(migration, prior_migrations / migration.name)
    assert await run_migrations(db, prior_migrations) == [migration.name]
    assert await owned(db, "memory", user_record(user.id)) == cards
    assert await owned(db, "review_log", user_record(user.id)) == logs
    loaded = await find_user(db, user.id)
    assert loaded is not None and loaded.prefs == prefs
    assert await repository.state(db, user.id) == {}
    now = datetime.now(UTC)
    run = await repository.claim(db, user.id, now)
    assert run is not None
    result = OptimizationRead(
        status="success", at=now, eligible_reviews=512, history_fingerprint="e" * 64
    )
    assert await repository.finish(db, user.id, run, result, list(DEFAULT_PARAMETERS))
    state = await repository.state(db, user.id)
    schema = await snapshot(db)
    assert await run_migrations(db, prior_migrations) == []
    await checked_query(db, migration.read_text(encoding="utf-8"))
    assert await snapshot(db) == schema
    assert await repository.state(db, user.id) == state
    assert await owned(db, "memory", user_record(user.id)) == cards
    assert await owned(db, "review_log", user_record(user.id)) == logs
    loaded = await find_user(db, user.id)
    assert loaded is not None and loaded.prefs == prefs


async def test_fresh_migration_indexes_and_owner_identity(
    db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    assert "0024_srs_optimization.surql" in await run_migrations(db)
    user, other = await make_user(), await make_user()
    with pytest.raises(MigrationError):
        await insert_foreign_identity(db, user.id, other.id)
    assert await repository.state(db, user.id) == {}
    assert await repository.state(db, other.id) == {}
    for table, index in (
        ("srs_optimization", "srs_optimization_owner"),
        ("memory", "memory_owner_last_review"),
        ("review_log", "review_log_owner_at"),
    ):
        assert index in (await table_info(db, table))["indexes"]


async def test_database_reads_recent_window_for_mature_cards(
    db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    await run_migrations(db)
    user = await make_user()
    source = history(user.id, cards=1, reviews=70)
    await seed(db, source)
    rows = await repository.history(db, user.id)
    logs, excluded = training_history(rows, user.id, datetime.now(UTC))
    assert len(rows) == 65 and len(logs) == 64 and excluded == 1
    assert rows[0]["at"] == source[-1]["at"] and rows[-1]["at"] == source[-65]["at"]
    assert datetime.fromisoformat(logs[0]["review_datetime"]) == source[-64]["at"]
    cards_plan, reviews_plan = await history_plans(db, user.id, rows[0]["memory"])
    card_scan = index_scan(cards_plan, "memory_owner_last_review")
    review_scan = index_scan(reviews_plan, "review_log_owner_at")
    assert card_scan is not None and card_scan["attributes"]["direction"] == "Backward"
    assert review_scan is not None and review_scan["attributes"]["direction"] == "Backward"
