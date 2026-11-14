import asyncio
from pathlib import Path
from typing import cast
from uuid import uuid4

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import create, relate, visible
from app.domain.dictionary_keys import lexeme_key, sense_key
from app.domain.identity import user_key
from app.services.dictionary import materialize_lemma, read_edges, read_entry, read_record
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory

# isort: split
from scripts.build_lexicon import build

# isort: split
from tests.unit.test_build_lexicon import entry, source_file
from tests.unit.test_lexicon_phrases import compound


async def test_shared_phrase_composition_literal_usage_and_owner_isolation(
    db: AsyncWsSurrealConnection, lexicon_reader: LexiconReader, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user()
    alice_id = RecordID("user", user_key(alice.id))
    bob_id = RecordID("user", user_key(bob.id))
    idiom = await materialize_lemma(
        db,
        lexicon_reader,
        "kick the bucket",
        selected_senses=[
            sense_key("en", "kick the bucket", "verb", source_sense_id="kick-bucket-die")
        ],
    )
    phrase = await materialize_lemma(db, lexicon_reader, "heavy rain")
    components = await read_edges(
        db, alice.id, idiom.lemma_id, "lemma", relation="contains", direction="outgoing"
    )
    assert sorted((edge.fields["position"], edge.end) for edge in components) == [
        (index, encode_rid(RecordID("lexeme", lexeme_key("en", word, pos)), "lexeme"))
        for index, (word, pos) in enumerate(
            [("kick", "verb"), ("the", "article"), ("bucket", "noun")]
        )
    ]
    assert all(edge.owner is None for edge in components)
    assert (
        await read_edges(
            db, alice.id, idiom.lemma_id, "lemma", relation="used_in", direction="incoming"
        )
        == []
    )
    entry = await read_entry(db, alice.id, idiom.lemma_id)
    assert entry is not None and entry.lemma.fields["kind"] == "phrase"
    assert [sense.fields["definition"] for item in entry.lexemes for sense in item.senses] == [
        "Die."
    ]
    usages = await read_edges(
        db, alice.id, phrase.lemma_id, "lemma", relation="used_in", direction="incoming"
    )
    assert {edge.start for edge in usages} == {
        encode_rid(RecordID("sense", sense_key("en", word, pos, source_sense_id=source)), "sense")
        for word, pos, source in [("heavy", "adj", "heavy-intense"), ("rain", "noun", "rain-water")]
    }
    assert all(edge.owner is None for edge in usages)
    heavy_weight = encode_rid(
        RecordID("sense", sense_key("en", "heavy", "adj", source_sense_id="heavy-weight")), "sense"
    )
    # Materializing the phrase does not select unrelated/common component senses.
    assert await read_record(db, alice.id, heavy_weight, "sense") is None
    public = await read_record(db, alice.id, components[0].end, "lexeme")
    assert public is not None
    private = RecordID("lexeme", uuid4().hex)
    await create(db, private, {**cast(dict[str, Value], public.fields), "owner": bob_id})
    phrase_id = decode_rid(idiom.lemma_id, "lemma")
    await relate(db, "contains", phrase_id, private, {"position": 80, "owner": None})
    await relate(db, "contains", phrase_id, private, {"position": 81, "owner": alice_id})
    private_edge = await relate(
        db,
        "contains",
        phrase_id,
        decode_rid(components[0].end, "lexeme"),
        {"position": 82, "owner": bob_id},
    )
    own_edge = await relate(
        db,
        "contains",
        phrase_id,
        decode_rid(components[0].end, "lexeme"),
        {"position": 83, "owner": alice_id},
    )
    private_usage = await relate(
        db, "used_in", decode_rid(usages[0].start, "sense"), phrase_id, {"owner": bob_id}
    )
    tables = ["lemma", "lexeme", "sense", "has_lexeme", "has_sense", "contains", "used_in"]
    before = {table: await visible(db, table, alice_id) for table in tables}
    for _ in range(2):
        assert (
            await materialize_lemma(
                db,
                lexicon_reader,
                "kick the bucket",
                selected_senses=[
                    sense_key("en", "kick the bucket", "verb", source_sense_id="kick-bucket-die")
                ],
            )
            == idiom
        )
        assert await materialize_lemma(db, lexicon_reader, "heavy rain") == phrase
    assert {table: await visible(db, table, alice_id) for table in tables} == before
    alice_edges = await read_edges(
        db, alice.id, idiom.lemma_id, "lemma", relation="contains", direction="outgoing"
    )
    assert {edge.id for edge in alice_edges} == {
        *(edge.id for edge in components),
        encode_rid(own_edge["id"], "contains"),
    }
    assert encode_rid(private_edge["id"], "contains") not in {edge.id for edge in alice_edges}
    assert (
        await read_edges(
            db, alice.id, idiom.lemma_id, "lemma", relation="used_in", direction="incoming"
        )
        == []
    )
    bob_edges = await read_edges(
        db, bob.id, idiom.lemma_id, "lemma", relation="contains", direction="outgoing"
    )
    assert encode_rid(private_edge["id"], "contains") in {edge.id for edge in bob_edges}
    assert encode_rid(own_edge["id"], "contains") not in {edge.id for edge in bob_edges}
    assert {
        edge.id
        for edge in await read_edges(
            db, bob.id, idiom.lemma_id, "lemma", relation="used_in", direction="incoming"
        )
    } == {encode_rid(private_usage["id"], "used_in")}


async def test_repeated_component_positions_and_concurrent_materialization(
    db: AsyncWsSurrealConnection, tmp_path: Path, make_user: UserFactory
) -> None:
    output = tmp_path / "repeated.sqlite"
    build(
        source_file(
            tmp_path,
            entry("rain rain", etymology_templates=[compound("rain", "rain")]),
            entry("rain", pos="noun"),
        ),
        output,
    )
    reader = LexiconReader(output)
    first, second = await asyncio.gather(
        materialize_lemma(db, reader, "rain rain", selected_senses=[]),
        materialize_lemma(db, reader, "rain rain", selected_senses=[]),
    )
    assert first == second and first.selected_sense_ids == []
    user = await make_user()
    edges = await read_edges(
        db, user.id, first.lemma_id, "lemma", relation="contains", direction="outgoing"
    )
    assert len(edges) == 2 and len({edge.id for edge in edges}) == 2
    assert {cast(int, edge.fields["position"]) for edge in edges} == {0, 1}
    assert {edge.end for edge in edges} == {
        encode_rid(RecordID("lexeme", lexeme_key("en", "rain", "noun")), "lexeme")
    }
