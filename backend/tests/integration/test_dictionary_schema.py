from uuid import uuid4

import pytest
from surrealdb import Null, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.dictionary_schema_test_support import create, relate, table_info, visible
from app.db.migrate import MIGRATIONS, run_migrations
from app.db.migration_store import MigrationError, checked_query
from app.db.migration_test_support import tables

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]

ROWS: dict[str, dict[str, Value]] = {
    "lemma": {
        "text": "run",
        "lang": "en",
        "kind": "word",
        "freq_zipf": 5.2,
        "cefr": "B1",
        "exam_tags": ["cet4"],
        "source": "wiktionary",
    },
    "lexeme": {
        "pos": "verb",
        "etymology_no": 1,
        "etymology_text": "Old English",
        "forms": [{"form": "ran", "tags": ["past"]}],
        "pron": [
            {"accent": "US", "ipa": "rʌn", "audio": RecordID("media", "audio")},
            {"accent": "UK", "ipa": "rʌn"},
        ],
    },
    "sense": {
        "definition": "move fast",
        "gloss": {"zh": "跑", "fr": "courir"},
        "register": [],
        "domain": ["motion"],
        "examples": ["Run!"],
        "rank": 0,
        "common": True,
        "source": "wiktionary",
    },
    "morpheme": {"text": "pre-", "type": "prefix", "meaning": "before"},
    "tag": {"kind": "custom", "name": "motion"},
    "sentence": {
        "text": "Run!",
        "lang": "en",
        "translation": {"zh": "跑！", "fr": "Cours !"},
        "source": "wiktionary",
    },
    "passage": {"title": "Running", "text": "Run!", "lang": "en", "source": "upload"},
}
EDGES: dict[str, tuple[list[str], list[str], dict[str, Value]]] = {
    "has_lexeme": (["lemma"], ["lexeme"], {}),
    "has_sense": (["lexeme"], ["sense"], {"rank": 0}),
    "composed_of": (["lexeme"], ["morpheme"], {"order": 0}),
    "derives_to": (["lexeme"], ["lexeme"], {"via": "suffix"}),
    "relates_to": (["sense"], ["sense"], {"type": "synonym", "source": "wiktionary"}),
    "member_of": (["sense", "morpheme", "tag"], ["tag"], {}),
    "contains": (["lemma"], ["lexeme"], {"position": 0}),
    "used_in": (["sense"], ["lemma", "sentence", "passage"], {"span": [0, 3]}),
    "part_of": (["sentence"], ["passage"], {"order": 0}),
}
FIELD_TYPES = {
    "lemma": {
        "string": "text lang source",
        "number": "freq_zipf",
        "none | string": "cefr",
        "'word' | 'phrase'": "kind",
        "array<string>": "exam_tags",
    },
    "lexeme": {
        "string": "pos forms.*.form pron.*.ipa",
        "int": "etymology_no",
        "none | string": "etymology_text",
        "array<object>": "forms pron",
        "array<string>": "forms.*.tags",
        "'US' | 'UK'": "pron.*.accent",
        "none | record<media>": "pron.*.audio",
    },
    "sense": {
        "string": "definition source gloss.*",
        "object FLEXIBLE": "gloss",
        "array<string>": "register domain examples",
        "int": "rank",
        "bool": "common",
    },
    "morpheme": {
        "string": "text",
        "none | string": "meaning",
        "'prefix' | 'root' | 'suffix' | 'infix'": "type",
    },
    "tag": {"string": "kind name"},
    "sentence": {"string": "text lang source translation.*", "object FLEXIBLE": "translation"},
    "passage": {"string": "title text lang source"},
    "has_sense": {"int": "rank"},
    "composed_of": {"int": "order"},
    "derives_to": {"none | string": "via"},
    "relates_to": {
        (
            "'synonym' | 'antonym' | 'hypernym' | 'hyponym' | "
            "'confusable' | 'collocation' | 'default'"
        ): "type",
        "string": "source",
    },
    "contains": {"int": "position"},
    "used_in": {"none | array<int, 2>": "span"},
    "part_of": {"int": "order"},
}


@pytest.fixture
async def dictionary_db(db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    assert "0005_dictionary.surql" in await run_migrations(db)
    return db


async def test_fresh_schema_and_repeat_are_identical(
    dictionary_db: AsyncWsSurrealConnection,
) -> None:
    db = dictionary_db
    before = {name: await table_info(db, name) for name in ROWS | EDGES}
    row = await create(db, RecordID("lemma", "retained"), ROWS["lemma"])
    assert await run_migrations(db) == []
    await checked_query(db, (MIGRATIONS / "0005_dictionary.surql").read_text(encoding="utf-8"))
    assert before == {name: await table_info(db, name) for name in before}
    assert await visible(db, "lemma", RecordID("user", "alice")) == [row]
    definitions = await tables(db)
    for name, info in before.items():
        assert "SCHEMAFULL" in definitions[name]
        assert "TYPE none | record<user>" in info["fields"]["owner"]
        for field_type, fields in FIELD_TYPES.get(name, {}).items():
            for field in fields.split():
                assert f"TYPE {field_type} PERMISSIONS" in info["fields"][field]
        if name in EDGES:
            assert "TYPE RELATION" in definitions[name]
            assert "ENFORCED" in definitions[name]
            start, end, _ = EDGES[name]
            for endpoint, expected in (("in", start), ("out", end)):
                actual = info["fields"][endpoint].split("TYPE record<")[1].split(">")[0]
                assert set(actual.split(" | ")) == set(expected)
    assert "FIELDS lang, text UNIQUE" in before["lemma"]["indexes"]["lemma_lang_text"]


@pytest.mark.parametrize("table", ROWS)
async def test_rows_round_trip_and_owner_isolation(
    dictionary_db: AsyncWsSurrealConnection,
    table: str,
) -> None:
    db = dictionary_db
    alice, bob = RecordID("user", "alice"), RecordID("user", "bob")
    shared = await create(db, RecordID(table, "shared"), ROWS[table])
    assert {key: shared[key] for key in ROWS[table]} == ROWS[table]
    assert shared.get("owner") is None
    for user in (alice, bob):
        data = {**ROWS[table], "owner": user}
        if table == "lemma":
            data["text"] = str(user)
        row = await create(db, RecordID(table, str(user)), data)
        assert row["owner"] == user
    assert {row["id"] for row in await visible(db, table, alice)} == {
        shared["id"],
        RecordID(table, str(alice)),
    }
    for owner in (RecordID("tag", "wrong"), "alice", Null):
        with pytest.raises(MigrationError):
            await create(db, RecordID(table, uuid4().hex), {**ROWS[table], "owner": owner})


@pytest.mark.parametrize("edge", EDGES)
async def test_relation_endpoints_fields_and_owner(
    dictionary_db: AsyncWsSurrealConnection,
    edge: str,
) -> None:
    db = dictionary_db
    starts, ends, attributes = EDGES[edge]
    records = {}
    for table in ROWS:
        records[table] = (await create(db, RecordID(table, "endpoint"), ROWS[table]))["id"]
    alice, bob = RecordID("user", "alice"), RecordID("user", "bob")
    for start in starts:
        for end in ends:
            for owner in (None, alice, bob):
                row = await relate(
                    db,
                    edge,
                    records[start],
                    records[end],
                    {
                        **attributes,
                        "owner": owner,
                    },
                )
                assert row["in"] == records[start] and row["out"] == records[end]
                assert row.get("owner") == owner
                assert {key: row[key] for key in attributes} == attributes
    shown = await visible(db, edge, alice)
    assert len(shown) == len(starts) * len(ends) * 2
    assert {row.get("owner") for row in shown} == {None, alice}
    if edge in ("derives_to", "used_in"):
        row = await relate(db, edge, records[starts[0]], records[ends[0]], {})
        assert row.get("via" if edge == "derives_to" else "span") is None
    for start, end, owner in (
        (records["passage"], records[ends[0]], None),
        (records[starts[0]], records["morpheme"], None),
        (RecordID(starts[0], "missing"), records[ends[0]], None),
        (records[starts[0]], RecordID(ends[0], "missing"), None),
        (records[starts[0]], records[ends[0]], RecordID("tag", "wrong")),
    ):
        # composed_of's valid output is morpheme; choose a different wrong target.
        if end == records["morpheme"] and "morpheme" in ends:
            end = records["passage"]
        with pytest.raises(MigrationError):
            await relate(db, edge, start, end, {**attributes, "owner": owner})


@pytest.mark.parametrize(
    ("table", "patch"),
    [
        ("lemma", {"kind": "idiom"}),
        ("lemma", {"freq_zipf": "five"}),
        ("lemma", {"cefr": 1}),
        ("lemma", {"exam_tags": [1]}),
        ("lemma", {"lang": None}),
        ("lexeme", {"etymology_no": 1.5}),
        ("lexeme", {"etymology_text": 1}),
        ("lexeme", {"forms": [{"form": "ran", "tags": [1]}]}),
        ("lexeme", {"forms": [{"tags": []}]}),
        ("lexeme", {"pron": [{"accent": "AU", "ipa": "rʌn"}]}),
        ("lexeme", {"pron": [{"accent": "UK", "ipa": "rʌn", "audio": RecordID("tag", "x")}]}),
        ("sense", {"gloss": {"zh": 1}}),
        ("sense", {"common": "true"}),
        ("sense", {"examples": [1]}),
        ("sense", {"rank": 0.5}),
        ("morpheme", {"type": "stem"}),
        ("morpheme", {"meaning": 1}),
        ("tag", {"name": 1}),
        ("sentence", {"translation": {"zh": 1}}),
        ("passage", {"title": 1}),
    ],
)
async def test_invalid_dictionary_fields_are_rejected(
    dictionary_db: AsyncWsSurrealConnection,
    table: str,
    patch: dict[str, Value],
) -> None:
    with pytest.raises(MigrationError):
        await create(dictionary_db, RecordID(table, uuid4().hex), {**ROWS[table], **patch})


async def test_lemma_natural_key_is_unique(dictionary_db: AsyncWsSurrealConnection) -> None:
    await create(dictionary_db, RecordID("lemma", "first"), ROWS["lemma"])
    with pytest.raises(MigrationError, match="lemma_lang_text"):
        await create(dictionary_db, RecordID("lemma", "second"), ROWS["lemma"])
    await create(dictionary_db, RecordID("lemma", "other-lang"), {**ROWS["lemma"], "lang": "fr"})


@pytest.mark.parametrize(
    ("edge", "patch"),
    [
        ("has_sense", {"rank": "first"}),
        ("composed_of", {"order": 0.5}),
        ("derives_to", {"via": 1}),
        ("relates_to", {"type": "translation"}),
        ("contains", {"position": "first"}),
        ("used_in", {"span": [0]}),
        ("used_in", {"span": [0, 1, 2]}),
        ("used_in", {"span": [0, "end"]}),
        ("part_of", {"order": 0.5}),
    ],
)
async def test_invalid_edge_fields_are_rejected(
    dictionary_db: AsyncWsSurrealConnection,
    edge: str,
    patch: dict[str, Value],
) -> None:
    starts, ends, attributes = EDGES[edge]
    for table in set(starts + ends):
        await create(dictionary_db, RecordID(table, "endpoint"), ROWS[table])
    with pytest.raises(MigrationError):
        await relate(
            dictionary_db,
            edge,
            RecordID(starts[0], "endpoint"),
            RecordID(ends[0], "endpoint"),
            {**attributes, **patch},
        )
