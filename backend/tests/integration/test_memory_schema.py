from datetime import UTC, datetime

import pytest
from surrealdb import Null, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.errors import AppError
from app.db.dictionary_schema_test_support import create, relate, table_info
from app.db.memory_schema_test_support import owned
from app.db.migrate import MIGRATIONS, run_migrations
from app.db.migration_store import MigrationError, checked_query
from app.db.project_schema_test_support import set_hidden
from app.db.projects import delete_project
from app.db.snapshot import snapshot
from app.domain.identity import user_subject
from tests.integration.test_project_schema import PROJECT

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]
ALICE, BOB = RecordID("user", "alice"), RecordID("user", "bob")
SENSE = RecordID("sense", "shared")
MEMORY = RecordID("memory", [ALICE, SENSE])
NOW = datetime(2026, 11, 14, 12, 30, 45, 123456, tzinfo=UTC)
CARD: dict[str, Value] = {
    "owner": ALICE,
    "sense": SENSE,
    "card_id": 1794659445123,
    "state": 1,
    "step": 0,
    "due": NOW,
    "introduced": False,
}
LOG: dict[str, Value] = {
    "owner": ALICE,
    "memory": MEMORY,
    "project": RecordID("project", "first"),
    "exercise": "cloze",
    "correct": True,
    "hint_used": False,
    "duration_ms": 3000,
    "auto_rating": 3,
    "rating": 4,
    "at": NOW,
    "is_introduction": True,
    "attempt_id": "opaque-attempt",
}
FIELDS = {
    "memory": {
        "record<user>": "owner",
        "record<sense>": "sense",
        "int": "card_id state",
        "none | int": "step",
        "none | float": "stability difficulty",
        "datetime": "due",
        "none | datetime": "last_review",
        "bool": "introduced",
    },
    "review_log": {
        "record<user>": "owner",
        "record<memory>": "memory",
        "record<project>": "project",
        "string": "exercise attempt_id",
        "bool": "correct hint_used is_introduction",
        "int": "duration_ms auto_rating rating",
        "datetime": "at",
    },
}


@pytest.fixture
async def memory_db(db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    assert "0013_memory_review_log.surql" in await run_migrations(db)
    return db


async def test_fresh_schema_types_indexes_and_replay(
    memory_db: AsyncWsSurrealConnection,
) -> None:
    db = memory_db
    card = await create(db, MEMORY, CARD)
    before = await snapshot(db)
    assert await run_migrations(db) == []
    await checked_query(db, (MIGRATIONS / "0013_memory_review_log.surql").read_text("utf-8"))
    assert await snapshot(db) == before
    assert await owned(db, "memory", ALICE) == [card]
    for table, types in FIELDS.items():
        info = await table_info(db, table)
        for kind, fields in types.items():
            for field in fields.split():
                assert f"TYPE {kind}" in info["fields"][field]
    for table, name, fields, unique in (
        ("memory", "memory_owner_sense", "owner, sense", True),
        ("memory", "memory_owner_due", "owner, due", False),
        ("review_log", "review_log_owner_at", "owner, at", False),
        ("review_log", "review_log_owner_attempt", "owner, attempt_id", True),
    ):
        definition = (await table_info(db, table))["indexes"][name]
        assert f"FIELDS {fields}" in definition
        assert ("UNIQUE" in definition) is unique


@pytest.mark.parametrize(
    "state,step,stability,difficulty,last_review",
    [(1, 0, None, None, None), (2, None, 7.125, 4.75, NOW), (3, 1, 0.125, 9.5, NOW)],
)
async def test_all_fsrs_card_fields_round_trip(
    memory_db: AsyncWsSurrealConnection,
    state: int,
    step: int | None,
    stability: float | None,
    difficulty: float | None,
    last_review: datetime | None,
) -> None:
    attributes = {
        **CARD,
        "state": state,
        "step": step,
        "stability": stability,
        "difficulty": difficulty,
        "last_review": last_review,
        "introduced": last_review is not None,
    }
    row = await create(memory_db, MEMORY, attributes)
    for field, value in attributes.items():
        assert row.get(field) == value
    assert await owned(memory_db, "memory", ALICE) == [row]


@pytest.mark.parametrize(
    "table,field,value",
    [
        ("memory", "owner", None),
        ("memory", "owner", Null),
        ("memory", "owner", RecordID("project", "wrong")),
        ("memory", "owner", BOB),
        ("memory", "sense", RecordID("sense", "wrong")),
        ("memory", "card_id", "not-an-int"),
        ("memory", "state", 4),
        ("memory", "step", -1),
        ("memory", "stability", "not-a-float"),
        ("memory", "difficulty", Null),
        ("memory", "due", "not-a-datetime"),
        ("memory", "last_review", Null),
        ("memory", "introduced", "yes"),
        ("review_log", "owner", None),
        ("review_log", "owner", BOB),
        ("review_log", "memory", RecordID("sense", "wrong")),
        ("review_log", "project", RecordID("user", "wrong")),
        ("review_log", "correct", "yes"),
        ("review_log", "hint_used", 1),
        ("review_log", "is_introduction", None),
        ("review_log", "duration_ms", -1),
        ("review_log", "duration_ms", 60001),
        ("review_log", "rating", 0),
        ("review_log", "auto_rating", 5),
        ("review_log", "at", None),
        ("review_log", "attempt_id", ""),
    ],
)
async def test_invalid_types_and_identity_are_rejected(
    memory_db: AsyncWsSurrealConnection, table: str, field: str, value: Value
) -> None:
    await create(memory_db, MEMORY, CARD)
    if table == "memory":
        # CREATE rejects duplicate IDs before content validation, so use a fresh sense/card.
        sense = RecordID("sense", "validation")
        record = RecordID("memory", [ALICE, sense])
        attributes = {**CARD, "sense": sense}
    else:
        record = RecordID("review_log", "validation")
        attributes = LOG
    with pytest.raises(MigrationError):
        await create(memory_db, record, {**attributes, field: value})


async def test_shared_card_two_users_projects_and_deletion(
    memory_db: AsyncWsSurrealConnection,
) -> None:
    db = memory_db
    # The schema does not enforce sense existence; ENFORCED includes does.
    await create(
        db,
        SENSE,
        {
            "definition": "shared meaning",
            "gloss": {},
            "register": [],
            "domain": [],
            "examples": [],
            "rank": 1,
            "common": True,
            "source": "user",
        },
    )
    first, second = RecordID("project", "first"), RecordID("project", "second")
    memberships = []
    for project in (first, second):
        await create(db, project, PROJECT)
        membership = await relate(
            db, "includes", project, SENSE, {"owner": ALICE, "hidden": False, "added_at": NOW}
        )
        memberships.append(membership)
    alice = await create(db, MEMORY, CARD)
    bob_memory = RecordID("memory", [BOB, SENSE])
    bob = await create(db, bob_memory, {**CARD, "owner": BOB})
    with pytest.raises(MigrationError):
        await create(db, MEMORY, CARD)
    with pytest.raises(MigrationError):
        await create(db, RecordID("memory", "arbitrary"), CARD)
    intro = await create(db, RecordID("review_log", "intro"), LOG)
    later = await create(
        db,
        RecordID("review_log", "later"),
        {
            **LOG,
            "project": second,
            "is_introduction": False,
            "attempt_id": "later-attempt",
            "hint_used": True,
            "duration_ms": 60000,
        },
    )
    with pytest.raises(MigrationError, match="review_log_owner_attempt"):
        await create(db, RecordID("review_log", "duplicate"), {**LOG, "project": second})
    bob_log = await create(
        db, RecordID("review_log", "bob"), {**LOG, "owner": BOB, "memory": bob_memory}
    )
    assert await owned(db, "memory", ALICE) == [alice]
    assert await owned(db, "memory", BOB) == [bob]
    assert await owned(db, "review_log", ALICE) == [intro, later]
    assert await owned(db, "review_log", BOB) == [bob_log]
    await set_hidden(db, memberships[0]["id"], ALICE, True)
    assert await owned(db, "memory", ALICE) == [alice]
    assert await owned(db, "review_log", ALICE) == [intro, later]
    await set_hidden(db, memberships[0]["id"], ALICE, False)
    for project in (first, second):
        with pytest.raises(AppError):
            await delete_project(db, user_subject("bob"), project)
        assert len(await owned(db, "project", ALICE)) > 0
        await delete_project(db, user_subject("alice"), project)
    assert await owned(db, "project", ALICE) == []
    assert await owned(db, "memory", ALICE) == [alice]
    assert await owned(db, "review_log", ALICE) == [intro, later]
    assert await owned(db, "memory", BOB) == [bob]
    assert await owned(db, "review_log", BOB) == [bob_log]
