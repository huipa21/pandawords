from datetime import UTC, datetime
from uuid import uuid4

import pytest
from surrealdb import Null, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.dictionary_schema_test_support import create, relate, table_info, visible
from app.db.migrate import MIGRATIONS, run_migrations
from app.db.migration_store import MigrationError, checked_query
from app.db.migration_test_support import tables
from app.db.project_schema_test_support import (
    owned,
    put_override,
    reset_override,
    set_hidden,
    visible_items,
)
from app.db.snapshot import snapshot
from tests.integration.test_dictionary_schema import ROWS

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]
ALICE, BOB = RecordID("user", "alice"), RecordID("user", "bob")
NOW = datetime(2026, 11, 14, tzinfo=UTC)
PROJECT: dict[str, Value] = {
    "owner": ALICE,
    "name": "English",
    "description": "Exam preparation",
    "target_lang": "en",
    "source_lang": "zh",
    "plan": {"daily_new": 10, "exam_date": NOW, "review_cap": 100},
    "created_at": NOW,
}
FIELDS = {
    "project": {
        "record<user>": "owner",
        "string": "name description target_lang source_lang",
        "object": "plan",
        "int": "plan.daily_new",
        "none | datetime": "plan.exam_date",
        "none | int": "plan.review_cap",
        "datetime": "created_at",
    },
    "includes": {"record<user>": "owner", "bool": "hidden", "datetime": "added_at"},
    "override": {
        "record<user>": "owner",
        "object FLEXIBLE": "fields",
        "datetime": "updated_at",
    },
    "note": {
        "record<user>": "owner",
        "record": "target",
        "'note' | 'mnemonic'": "kind",
        "string": "text",
    },
}


@pytest.fixture
async def project_db(db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    assert "0006_project_overlays.surql" in await run_migrations(db)
    return db


async def test_fresh_schema_replay_and_drift(project_db: AsyncWsSurrealConnection) -> None:
    db = project_db
    row = await create(db, RecordID("project", "retained"), PROJECT)
    before = await snapshot(db)
    assert await run_migrations(db) == []
    await checked_query(db, (MIGRATIONS / "0006_project_overlays.surql").read_text("utf-8"))
    assert await snapshot(db) == before
    assert await owned(db, "project", ALICE) == [row]
    definitions = await tables(db)
    for table, field_types in FIELDS.items():
        assert "SCHEMAFULL" in definitions[table]
        info = await table_info(db, table)
        for field_type, names in field_types.items():
            for name in names.split():
                assert f"TYPE {field_type} PERMISSIONS" in info["fields"][name]
    info = await table_info(db, "includes")
    assert "TYPE RELATION IN project OUT" in definitions["includes"]
    assert "ENFORCED" in definitions["includes"]
    assert "TYPE record<project>" in info["fields"]["in"]
    targets = info["fields"]["out"].split("TYPE record<")[1].split(">")[0]
    assert set(targets.split(" | ")) == {"lemma", "sense", "sentence", "passage"}
    for table, index, fields in (
        ("project", "project_owner", "owner"),
        ("note", "note_owner_target", "owner, target"),
    ):
        assert f"FIELDS {fields}" in (await table_info(db, table))["indexes"][index]
    optional = await create(
        db, RecordID("project", "optional"), {**PROJECT, "plan": {"daily_new": 0}}
    )
    assert optional["plan"] == {"daily_new": 0}


async def test_membership_endpoints_restore_and_visibility(
    project_db: AsyncWsSurrealConnection,
) -> None:
    db = project_db
    project = (await create(db, RecordID("project", "alice"), PROJECT))["id"]
    other = (await create(db, RecordID("project", "bob"), {**PROJECT, "owner": BOB}))["id"]
    attributes: dict[str, Value] = {"owner": ALICE, "hidden": False, "added_at": NOW}
    for table in ("lemma", "sense", "sentence", "passage"):
        target = (await create(db, RecordID(table, "item"), ROWS[table]))["id"]
        edge = await relate(db, "includes", project, target, attributes)
        assert edge["in"] == project and edge["out"] == target
        assert edge["added_at"] == NOW
        assert await set_hidden(db, edge["id"], BOB, True) == []
        assert (await set_hidden(db, edge["id"], ALICE, True))[0]["hidden"] is True
        assert edge["id"] not in {row["id"] for row in await visible_items(db, project, ALICE)}
        restored = (await set_hidden(db, edge["id"], ALICE, False))[0]
        assert restored == edge
        assert target in {row["id"] for row in await visible(db, table, ALICE)}
        assert await visible_items(db, project, BOB) == []
    assert len(await visible_items(db, project, ALICE)) == 4
    private = (await create(db, RecordID("sense", "private"), {**ROWS["sense"], "owner": BOB}))[
        "id"
    ]
    await relate(db, "includes", project, private, attributes)
    await relate(db, "includes", other, private, {**attributes, "owner": BOB})
    assert len(await visible_items(db, project, ALICE)) == 4
    assert await visible_items(db, other, ALICE) == []
    lexeme = (await create(db, RecordID("lexeme", "wrong"), ROWS["lexeme"]))["id"]
    for start, end in (
        (lexeme, private),
        (project, lexeme),
        (RecordID("project", "missing"), private),
        (project, RecordID("sense", "missing")),
    ):
        with pytest.raises(MigrationError):
            await relate(db, "includes", start, end, attributes)


async def test_override_identity_partial_objects_and_reset(
    project_db: AsyncWsSurrealConnection,
) -> None:
    db = project_db
    target = RecordID("sense", "shared")
    original = await create(db, target, ROWS["sense"])
    fields: dict[str, Value] = {"gloss": {"zh": "奔跑"}, "examples": ["Run now!"]}
    first = await put_override(db, ALICE, target, fields)
    assert first["id"] == RecordID("override", [ALICE, target])
    assert first["fields"] == fields and first["owner"] == ALICE
    assert first["updated_at"].tzinfo is not None
    with pytest.raises(MigrationError):
        await create(db, first["id"], {k: v for k, v in first.items() if k != "id"})
    changed = await put_override(db, ALICE, target, {"definition": "sprint"})
    assert changed["id"] == first["id"] and changed["fields"] == {"definition": "sprint"}
    bob = await put_override(db, BOB, target, {"definition": "Bob's edit"})
    second = await put_override(db, ALICE, RecordID("sense", "another"), {})
    assert {row["id"] for row in await owned(db, "override", ALICE)} == {first["id"], second["id"]}
    assert await owned(db, "override", BOB) == [bob]
    await reset_override(db, ALICE, target)
    assert await owned(db, "override", ALICE) == [second]
    assert await owned(db, "override", BOB) == [bob]
    assert await visible(db, "sense", ALICE) == [original]


async def test_note_ownership_and_arbitrary_record_target(
    project_db: AsyncWsSurrealConnection,
) -> None:
    db = project_db
    target = RecordID("tag", "any-record")
    for user in (ALICE, BOB):
        for kind in ("note", "mnemonic"):
            row = await create(
                db,
                RecordID("note", uuid4().hex),
                {"owner": user, "target": target, "kind": kind, "text": "Remember!"},
            )
            assert row["owner"] == user and row["target"] == target
    assert len(await owned(db, "note", ALICE)) == 2
    assert {row["owner"] for row in await owned(db, "note", ALICE)} == {ALICE}
    assert {row["owner"] for row in await owned(db, "note", BOB)} == {BOB}


@pytest.mark.parametrize(
    ("table", "patch"),
    [
        ("project", {"name": 1}),
        ("project", {"description": None}),
        ("project", {"target_lang": 1}),
        ("project", {"source_lang": 1}),
        ("project", {"plan": {}}),
        ("project", {"plan": {"daily_new": 1.5}}),
        ("project", {"plan": {"daily_new": 1, "review_cap": "many"}}),
        ("project", {"plan": {"daily_new": 1, "exam_date": "2026-11-14"}}),
        ("project", {"created_at": "today"}),
        ("override", {"fields": []}),
        ("override", {"updated_at": "now"}),
        ("note", {"target": "sense:run"}),
        ("note", {"kind": "comment"}),
        ("note", {"text": 1}),
    ],
)
async def test_invalid_overlay_fields(
    project_db: AsyncWsSurrealConnection, table: str, patch: dict[str, Value]
) -> None:
    data: dict[str, dict[str, Value]] = {
        "project": PROJECT,
        "override": {"owner": ALICE, "fields": {}, "updated_at": NOW},
        "note": {"owner": ALICE, "target": ALICE, "kind": "note", "text": "hi"},
    }
    with pytest.raises(MigrationError):
        await create(project_db, RecordID(table, uuid4().hex), {**data[table], **patch})


@pytest.mark.parametrize("table", FIELDS)
async def test_all_overlay_owners_are_required_user_references(
    project_db: AsyncWsSurrealConnection, table: str
) -> None:
    db = project_db
    data: dict[str, dict[str, Value]] = {
        "project": PROJECT,
        "includes": {"owner": ALICE, "hidden": False, "added_at": NOW},
        "override": {"owner": ALICE, "fields": {}, "updated_at": NOW},
        "note": {"owner": ALICE, "target": ALICE, "kind": "note", "text": "hi"},
    }
    project = (await create(db, RecordID("project", "endpoint"), PROJECT))["id"]
    sense = (await create(db, RecordID("sense", "endpoint"), ROWS["sense"]))["id"]
    patches = [{"owner": owner} for owner in (None, Null, "alice", RecordID("tag", "x"))]
    if table == "includes":
        patches.extend([{"hidden": "false"}, {"added_at": "today"}])
    for patch in patches:
        with pytest.raises(MigrationError):
            if table == "includes":
                await relate(db, table, project, sense, {**data[table], **patch})
            else:
                await create(db, RecordID(table, uuid4().hex), {**data[table], **patch})
