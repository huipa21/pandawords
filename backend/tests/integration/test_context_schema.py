from uuid import uuid4

import pytest
from surrealdb import Null, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.dictionary_schema_test_support import create, relate, visible
from app.db.migrate import MIGRATIONS, run_migrations
from app.db.migration_store import MigrationError, checked_query
from app.db.snapshot import snapshot

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]

CONTEXT: dict[str, dict[str, Value]] = {
    "sentence": {
        "text": "Run! 跑！",
        "lang": "en",
        "translation": {"zh": "跑！", "fr": "Cours !"},
        "source": "upload",
    },
    "passage": {"title": "Running", "text": "Run! 跑！", "lang": "en", "source": "upload"},
}
SENSE: dict[str, Value] = {
    "definition": "move fast",
    "gloss": {"zh": "跑"},
    "register": [],
    "domain": [],
    "examples": [],
    "rank": 0,
    "common": True,
    "source": "fixture",
}


@pytest.fixture
async def context_db(db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    assert "0005_dictionary.surql" in await run_migrations(db)
    return db


async def test_populated_context_survives_migration_replay(
    context_db: AsyncWsSurrealConnection,
) -> None:
    db = context_db
    alice = RecordID("user", "alice")
    passage = RecordID("passage", "private")
    await create(db, passage, {**CONTEXT["passage"], "owner": alice})
    # Insert out of reading order; order is persisted metadata, not insertion order.
    for order in (2, 0, 1):
        sentence = RecordID("sentence", str(order))
        await create(db, sentence, {**CONTEXT["sentence"], "owner": alice})
        await relate(db, "part_of", sentence, passage, {"order": order, "owner": alice})
    sense = RecordID("sense", "run")
    await create(db, sense, SENSE)
    await relate(db, "used_in", sense, passage, {"owner": alice})
    await relate(db, "used_in", sense, RecordID("sentence", "0"), {"span": [0, 3], "owner": alice})
    before_schema = await snapshot(db)
    before_rows = {
        table: await visible(db, table, alice)
        for table in ("sentence", "passage", "part_of", "used_in")
    }

    assert await run_migrations(db) == []
    await checked_query(db, (MIGRATIONS / "0005_dictionary.surql").read_text(encoding="utf-8"))

    assert await snapshot(db) == before_schema
    assert {table: await visible(db, table, alice) for table in before_rows} == before_rows
    ordered = sorted(before_rows["part_of"], key=lambda edge: edge["order"])
    assert [edge["in"] for edge in ordered] == [
        RecordID("sentence", str(order)) for order in range(3)
    ]
    assert sorted(edge.get("span", []) for edge in before_rows["used_in"]) == [[], [0, 3]]


@pytest.mark.parametrize(
    ("table", "field"),
    [(table, field) for table, content in CONTEXT.items() for field in content],
)
async def test_context_required_fields_reject_omission_and_null(
    context_db: AsyncWsSurrealConnection, table: str, field: str
) -> None:
    for value in (None, Null):
        content = dict(CONTEXT[table])
        if value is None:
            del content[field]
        else:
            content[field] = value
        with pytest.raises(MigrationError, match=field):
            await create(context_db, RecordID(table, uuid4().hex), content)


@pytest.mark.parametrize(
    ("table", "patch"),
    [
        ("sentence", {"text": 1}),
        ("sentence", {"lang": ["en"]}),
        ("sentence", {"source": 1}),
        ("sentence", {"translation": []}),
        ("sentence", {"translation": {"zh": Null}}),
        ("sentence", {"translation": {"zh": {"text": "跑！"}}}),
        ("passage", {"text": 1}),
        ("passage", {"lang": ["en"]}),
        ("passage", {"source": 1}),
    ],
)
async def test_context_field_types_reject_invalid_values(
    context_db: AsyncWsSurrealConnection, table: str, patch: dict[str, Value]
) -> None:
    with pytest.raises(MigrationError):
        await create(context_db, RecordID(table, uuid4().hex), {**CONTEXT[table], **patch})


@pytest.mark.parametrize("table", CONTEXT)
async def test_context_schemafull_preserves_languages_and_rejects_unknown_fields(
    context_db: AsyncWsSurrealConnection, table: str
) -> None:
    with pytest.raises(MigrationError, match="undeclared"):
        await create(
            context_db,
            RecordID(table, uuid4().hex),
            {**CONTEXT[table], "undeclared": "reject me"},
        )
    row = await create(context_db, RecordID(table, uuid4().hex), CONTEXT[table])
    assert {field: row[field] for field in CONTEXT[table]} == CONTEXT[table]
    assert "undeclared" not in row
    assert row.get("owner") is None
    if table == "sentence":
        untranslated = await create(
            context_db,
            RecordID(table, uuid4().hex),
            {**CONTEXT[table], "translation": {}},
        )
        assert untranslated["translation"] == {}


@pytest.mark.parametrize("span", [Null, [], [0, 1.5], [False, 3], "0,3"])
async def test_occurrence_span_rejects_non_integer_pairs(
    context_db: AsyncWsSurrealConnection, span: Value
) -> None:
    sense = RecordID("sense", "run")
    await create(context_db, sense, SENSE)
    sentence = RecordID("sentence", "example")
    await create(context_db, sentence, CONTEXT["sentence"])
    with pytest.raises(MigrationError, match="span"):
        await relate(context_db, "used_in", sense, sentence, {"span": span})


@pytest.mark.parametrize("order", [None, Null, "first", False])
async def test_passage_membership_requires_integer_order(
    context_db: AsyncWsSurrealConnection, order: Value
) -> None:
    sentence, passage = RecordID("sentence", "example"), RecordID("passage", "example")
    await create(context_db, sentence, CONTEXT["sentence"])
    await create(context_db, passage, CONTEXT["passage"])
    with pytest.raises(MigrationError, match="order"):
        await relate(context_db, "part_of", sentence, passage, {"order": order})


async def test_endpoint_enforcement_does_not_authorize_context_owners(
    context_db: AsyncWsSurrealConnection,
) -> None:
    db = context_db
    alice, bob = RecordID("user", "alice"), RecordID("user", "bob")
    sentence, passage = RecordID("sentence", "bobs"), RecordID("passage", "alices")
    await create(db, sentence, {**CONTEXT["sentence"], "owner": bob})
    await create(db, passage, {**CONTEXT["passage"], "owner": alice})
    edge = await relate(db, "part_of", sentence, passage, {"order": 0, "owner": alice})
    # Typed/existing endpoints and an owner-filtered edge do not authorize the endpoint.
    assert await visible(db, "part_of", alice) == [edge]
    assert await visible(db, "sentence", alice) == []
    assert await visible(db, "passage", bob) == []
    assert await visible(db, "part_of", bob) == []
    assert edge["in"] == sentence and edge["out"] == passage
    sense = RecordID("sense", "bobs")
    await create(db, sense, {**SENSE, "owner": bob})
    occurrence = await relate(db, "used_in", sense, passage, {"owner": alice})
    assert await visible(db, "used_in", alice) == [occurrence]
    assert await visible(db, "sense", alice) == []
