import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import create, relate, visible
from app.domain.dictionary_keys import lexeme_key, sense_key
from app.domain.identity import user_key
from app.services.dictionary import (
    materialize_lemma,
    read_edges,
    read_entry,
    read_record,
    read_records,
)
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory


async def test_selected_materialization_is_repeatable_and_preserves_overlays(
    db: AsyncWsSurrealConnection, lexicon_reader: LexiconReader, make_user: UserFactory
) -> None:
    alice = await make_user()
    bob = await make_user()
    alice_id = RecordID("user", user_key(alice.id))
    bob_id = RecordID("user", user_key(bob.id))
    key = sense_key("en", "run", "verb", source_sense_id="run-move")
    result = await materialize_lemma(db, lexicon_reader, " ＲＵＮ ", selected_senses=[key, key])
    assert len(result.lexeme_ids) == 2 and len(result.selected_sense_ids) == 1
    target = decode_rid(result.selected_sense_ids[0], "sense")
    lexeme = RecordID("lexeme", lexeme_key("en", "run", "verb"))
    original = await read_record(db, alice.id, result.selected_sense_ids[0], "sense")
    assert original is not None
    assert original.fields["definition"] == "Move quickly on foot."
    assert original.fields["examples"] == ["We run every morning."]
    assert original.fields["gloss"] == {"zh": "跑"}
    custom = RecordID("sense", uuid4().hex)
    await create(db, custom, {**cast(dict[str, Value], original.fields), "owner": alice_id})
    await relate(db, "has_sense", lexeme, custom, {"rank": 99, "owner": alice_id})
    await create(
        db,
        RecordID("override", [alice_id, target]),
        {
            "owner": alice_id,
            "fields": {
                "definition": "Alice's explanation",
                "gloss": {"fr": "courir"},
                "id": "not-an-id",
                "owner": bob_id,
            },
            "updated_at": datetime.now(UTC),
        },
    )
    await create(
        db,
        RecordID("override", [bob_id, target]),
        {
            "owner": bob_id,
            "fields": {"definition": "Bob's explanation"},
            "updated_at": datetime.now(UTC),
        },
    )
    bob_effective = await read_record(db, bob.id, original.id, "sense")
    assert bob_effective is not None
    assert bob_effective.fields["definition"] == "Bob's explanation"
    tables = ["lemma", "lexeme", "sense", "has_lexeme", "has_sense", "tag", "member_of", "override"]
    before = {table: await visible(db, table, alice_id) for table in tables}
    for _ in range(2):
        assert await materialize_lemma(db, lexicon_reader, "run", selected_senses=[key]) == result
    assert {table: await visible(db, table, alice_id) for table in tables} == before
    effective = await read_record(db, alice.id, original.id, "sense")
    assert effective is not None and effective.id == original.id and effective.owner is None
    assert effective.fields["definition"] == "Alice's explanation"
    assert effective.fields["gloss"] == {"zh": "跑", "fr": "courir"}
    assert "owner" not in effective.fields and "id" not in effective.fields
    assert await read_record(db, bob.id, original.id, "sense") == bob_effective
    shared = next(row for row in await visible(db, "sense", alice_id) if row["id"] == target)
    assert shared["definition"] == original.fields["definition"] and shared["gloss"] == {"zh": "跑"}
    assert {table: await visible(db, table, alice_id) for table in tables} == before
    entry = await read_entry(db, alice.id, result.lemma_id)
    assert entry is not None
    assert {sense.id for item in entry.lexemes for sense in item.senses} == {
        original.id,
        encode_rid(custom, "sense"),
    }
    expanded = await materialize_lemma(db, lexicon_reader, "run")
    assert len(expanded.selected_sense_ids) == 3  # noun + two common verb senses
    rare = sense_key("en", "run", "verb", source_sense_id="run-flow")
    enriched = await materialize_lemma(db, lexicon_reader, "run", selected_senses=[rare])
    assert enriched.selected_sense_ids == [encode_rid(RecordID("sense", rare), "sense")]
    assert await read_record(db, alice.id, original.id, "sense") == effective


async def test_each_endpoint_and_edge_is_owner_filtered(
    db: AsyncWsSurrealConnection, lexicon_reader: LexiconReader, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user()
    alice_id, bob_id = RecordID("user", user_key(alice.id)), RecordID("user", user_key(bob.id))
    result = await materialize_lemma(db, lexicon_reader, "bank")
    shared = decode_rid(result.selected_sense_ids[0], "sense")
    stored = await read_record(db, alice.id, result.selected_sense_ids[0], "sense")
    assert stored is not None
    await create(
        db,
        RecordID("override", [alice_id, shared]),
        {
            "owner": bob_id,
            "fields": {"definition": "Not Alice's override"},
            "updated_at": datetime.now(UTC),
        },
    )
    assert await read_record(db, alice.id, stored.id, "sense") == stored
    source = decode_rid(result.lexeme_ids[0], "lexeme")
    alice_sense, bob_sense = RecordID("sense", uuid4().hex), RecordID("sense", uuid4().hex)
    for record, user in ((alice_sense, alice_id), (bob_sense, bob_id)):
        await create(db, record, {**cast(dict[str, Value], stored.fields), "owner": user})
        await relate(db, "has_sense", source, record, {"rank": 10, "owner": user})
    # Shared/matching-owner edges cannot make a foreign endpoint visible.
    await relate(db, "has_sense", source, bob_sense, {"rank": 11, "owner": None})
    await relate(db, "has_sense", source, bob_sense, {"rank": 12, "owner": alice_id})
    foreign_shared_edge = await relate(
        db, "has_sense", source, shared, {"rank": 13, "owner": bob_id}
    )
    private_lexeme = RecordID("lexeme", uuid4().hex)
    public_lexeme = await read_record(db, alice.id, result.lexeme_ids[0], "lexeme")
    assert public_lexeme is not None
    await create(
        db, private_lexeme, {**cast(dict[str, Value], public_lexeme.fields), "owner": bob_id}
    )
    await relate(
        db, "has_lexeme", decode_rid(result.lemma_id, "lemma"), private_lexeme, {"owner": None}
    )
    await relate(db, "has_sense", private_lexeme, shared, {"rank": 1, "owner": alice_id})
    for user, own, foreign in ((alice, alice_sense, bob_sense), (bob, bob_sense, alice_sense)):
        entry = await read_entry(db, user.id, result.lemma_id)
        assert entry is not None and entry.lemma.owner is None
        senses = {sense.id for item in entry.lexemes for sense in item.senses}
        assert encode_rid(own, "sense") in senses
        assert encode_rid(foreign, "sense") not in senses
        assert await read_record(db, user.id, encode_rid(foreign, "sense"), "sense") is None
    assert await read_record(db, alice.id, encode_rid(private_lexeme, "lexeme"), "lexeme") is None
    edges = await read_edges(
        db, alice.id, result.lexeme_ids[0], "lexeme", relation="has_sense", direction="outgoing"
    )
    assert encode_rid(foreign_shared_edge["id"], "has_sense") not in {edge.id for edge in edges}
    assert encode_rid(bob_sense, "sense") not in {edge.end for edge in edges}
    assert encode_rid(alice_sense, "sense") in {edge.end for edge in edges}
    incoming = await read_edges(db, alice.id, stored.id, "sense", relation="has_sense")
    assert encode_rid(private_lexeme, "lexeme") not in {edge.start for edge in incoming}
    assert await read_edges(db, alice.id, encode_rid(bob_sense, "sense"), "sense") == []
    assert await read_records(
        db, alice.id, [("sense", encode_rid(bob_sense, "sense")), ("sense", stored.id)]
    ) == [stored]


async def test_affixes_and_relations_are_idempotent_without_recursive_expansion(
    db: AsyncWsSurrealConnection, lexicon_reader: LexiconReader, make_user: UserFactory
) -> None:
    user = await make_user()
    decision, simultaneous = await asyncio.gather(
        materialize_lemma(db, lexicon_reader, "decision", selected_senses=[]),
        materialize_lemma(db, lexicon_reader, "decision", selected_senses=[]),
    )
    assert decision == simultaneous and decision.selected_sense_ids == []
    entry = await read_entry(db, user.id, decision.lemma_id)
    assert entry is not None and all(not item.senses for item in entry.lexemes)
    affixes = await read_edges(
        db, user.id, decision.lexeme_ids[0], "lexeme", relation="composed_of"
    )
    assert sorted(cast(int, edge.fields["order"]) for edge in affixes) == [0, 1]
    assert len(affixes) == 2
    all_edges = await read_edges(db, user.id, decision.lexeme_ids[0], "lexeme")
    assert {edge.id for edge in affixes} < {edge.id for edge in all_edges}
    await materialize_lemma(db, lexicon_reader, "decision", selected_senses=[])
    assert (
        await read_edges(db, user.id, decision.lexeme_ids[0], "lexeme", relation="composed_of")
        == affixes
    )
    happy = await materialize_lemma(db, lexicon_reader, "happy")
    assert (
        await read_edges(db, user.id, happy.selected_sense_ids[0], "sense", relation="relates_to")
        == []
    )
    joyful = await materialize_lemma(
        db,
        lexicon_reader,
        "joyful",
        selected_senses=[sense_key("en", "joyful", "adj", source_sense_id="joyful-pleased")],
    )
    relations = await read_edges(
        db,
        user.id,
        happy.selected_sense_ids[0],
        "sense",
        relation="relates_to",
        direction="outgoing",
    )
    assert len(relations) == 1 and relations[0].fields == {"type": "synonym", "source": "oewn"}
    assert relations[0].end == joyful.selected_sense_ids[0]
    assert (
        await read_edges(
            db,
            user.id,
            joyful.selected_sense_ids[0],
            "sense",
            relation="relates_to",
            direction="incoming",
        )
        == relations
    )
    assert (
        len(
            await read_edges(
                db, user.id, happy.selected_sense_ids[0], "sense", relation="relates_to"
            )
        )
        == 2
    )
    await materialize_lemma(db, lexicon_reader, "happy")
    assert (
        await read_edges(
            db,
            user.id,
            happy.selected_sense_ids[0],
            "sense",
            relation="relates_to",
            direction="outgoing",
        )
        == relations
    )


async def test_invalid_selection_has_no_partial_writes_and_identity_conflicts_are_safe(
    db: AsyncWsSurrealConnection, lexicon_reader: LexiconReader, make_user: UserFactory
) -> None:
    user = await make_user()
    user_id = RecordID("user", user_key(user.id))
    with pytest.raises(AppError) as error:
        await materialize_lemma(
            db, lexicon_reader, "dog", selected_senses=[["en", "not-a-dog-sense"]]
        )
    assert error.value.status == 422
    dog_id = encode_rid(RecordID("lemma", ["en", "dog"]), "lemma")
    assert await read_entry(db, user.id, dog_id) is None
    conflict = RecordID("lexeme", lexeme_key("en", "dog", "noun"))
    await create(
        db,
        conflict,
        {
            "pos": "noun",
            "etymology_no": 1,
            "forms": [],
            "pron": [],
            "owner": user_id,
        },
    )
    with pytest.raises(AppError) as error:
        await materialize_lemma(db, lexicon_reader, "dog")
    assert error.value.status == 409
    assert await read_entry(db, user.id, dog_id) is None
    custom = await read_record(db, user.id, encode_rid(conflict, "lexeme"), "lexeme")
    assert custom is not None and custom.owner == user.id
    with pytest.raises(AppError) as error:
        await materialize_lemma(db, lexicon_reader, "not-in-the-fixture")
    assert error.value.status == 404
