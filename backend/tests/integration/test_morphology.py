import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError, LlmUnavailable
from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import create, relate, visible
from app.domain.add_to_project import EnrichJobPayload
from app.domain.auth import UserCreate
from app.domain.dictionary_keys import DictionaryKey, lexeme_key
from app.domain.identity import user_key
from app.domain.llm import LlmResult
from app.services.auth import create_user
from app.services.dictionary import materialize_lemma
from app.services.enrichment import enrich
from app.services.lexicon import LexiconReader
from app.services.morphology import (
    Component,
    Proposal,
    prepare_morphology,
    read_group_members,
    read_morphemes,
)

# isort: split
from scripts.build_lexicon import build

pytestmark = pytest.mark.integration


@pytest.fixture
def morphology_reader(tmp_path: Path) -> LexiconReader:
    def entry(word: str, pos: str = "noun", templates=None):
        return {
            "word": word,
            "pos": pos,
            "lang_code": "en",
            "senses": [{"id": word, "glosses": ["Meaning of " + word]}],
            "etymology_templates": templates,
        }

    def template(name: str, *parts: str):
        return {
            "name": name,
            "args": {"1": "en", **{str(i + 2): part for i, part in enumerate(parts)}},
        }

    records = [
        entry("decide", "verb"),
        entry("-ion", "suffix"),
        entry("re-", "prefix"),
        entry("echo"),
        entry("-in-", "infix"),
        entry("echoinecho", templates=[template("affix", "echo", "-in-", "echo")]),
        entry("decision", templates=[template("suffix", "decide", "ion")]),
        entry("redecide", templates=[template("prefix", "re", "decide")]),
        entry("echoecho", templates=[template("compound", "echo", "echo")]),
        entry("unanalysed"),
        entry("ambiguous-root"),
        {**entry("ambiguous-root"), "etymology_number": 2},
        entry("ambiguous", templates=[template("suffix", "ambiguous-root", "ion")]),
        entry("missing", templates=[template("suffix", "unknown", "ion")]),
        entry(
            "conflicting",
            templates=[template("suffix", "decide", "ion"), template("prefix", "re", "decide")],
        ),
    ]
    source, output = tmp_path / "source.jsonl", tmp_path / "morphology.sqlite"
    source.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    build(source, output)
    return LexiconReader(output)


async def materialized(
    db: AsyncWsSurrealConnection, reader: LexiconReader, word: str
) -> EnrichJobPayload:
    lemma = await reader.get_lemma(word)
    assert lemma is not None
    lexemes = await reader.lexemes(lemma.id)
    senses = await reader.senses(lexemes[0].id)
    result = await materialize_lemma(db, reader, word, selected_senses=[senses[0].id])
    return EnrichJobPayload(
        lemma_key=["en", word],
        lemma_id=result.lemma_id,
        lexeme_id=result.lexeme_ids[0],
        sense_id=result.selected_sense_ids[0],
    )


async def owner(db: AsyncWsSurrealConnection) -> str:
    return (
        await create_user(db, UserCreate(username="morph_" + uuid4().hex, password="test-password"))
    ).id


async def test_source_order_repeat_provenance_groups_and_insert_only(
    job_db: AsyncWsSurrealConnection, morphology_reader: LexiconReader
) -> None:
    user = await owner(job_db)
    selected = []
    for word in ("decision", "redecide", "echoecho", "echoinecho"):
        payload = await materialized(job_db, morphology_reader, word)
        await enrich(job_db, morphology_reader, payload)
        selected.append(payload)
    before = await visible(job_db, "composed_of", None)
    assert len(before) == 9
    for payload in selected:
        await enrich(job_db, morphology_reader, payload)
    assert await visible(job_db, "composed_of", None) == before
    decision = await read_morphemes(job_db, user, selected[0].lexeme_id)
    assert [(part.text, part.type, part.order, part.source) for part in decision] == [
        ("decide", "root", 0, "wiktionary"),
        ("-ion", "suffix", 1, "wiktionary"),
    ]
    repeated = await read_morphemes(job_db, user, selected[2].lexeme_id)
    assert [part.order for part in repeated] == [0, 1]
    assert repeated[0].id == repeated[1].id
    infixed = await read_morphemes(job_db, user, selected[3].lexeme_id)
    assert [part.type for part in infixed] == ["root", "infix", "root"]
    members = await read_group_members(job_db, user, selected[0].sense_id, "sense")
    assert encode_rid(RecordID("morpheme", ["en", "decide", "root", 1]), "morpheme") in {
        row.id for row in members
    }
    assert selected[1].sense_id in {row.id for row in members}
    assert selected[2].sense_id not in {row.id for row in members}
    assert members == await read_group_members(job_db, user, selected[0].sense_id, "sense")
    assert all(part.readonly for part in decision)


async def test_missing_conflicting_and_no_spelling_guesses(
    job_db: AsyncWsSurrealConnection, morphology_reader: LexiconReader, tmp_path: Path
) -> None:
    for word in ("missing", "conflicting", "unanalysed", "ambiguous"):
        await enrich(job_db, morphology_reader, await materialized(job_db, morphology_reader, word))
    assert await visible(job_db, "morpheme", None) == []
    assert await visible(job_db, "composed_of", None) == []
    assert await visible(job_db, "member_of", None) == []
    with closing(sqlite3.connect(tmp_path / "morphology.sqlite")) as connection:
        connection.execute("UPDATE morphology_analysis SET components = '[]'")
        connection.commit()
    await materialized(job_db, morphology_reader, "decision")
    assert await visible(job_db, "morpheme", None) == []


async def test_owner_filters_edges_endpoints_tags_and_private_morphology(
    job_db: AsyncWsSurrealConnection, morphology_reader: LexiconReader
) -> None:
    alice, bob = await owner(job_db), await owner(job_db)
    a, b = RecordID("user", user_key(alice)), RecordID("user", user_key(bob))
    payload = await materialized(job_db, morphology_reader, "decision")
    await enrich(job_db, morphology_reader, payload)
    lexeme, sense = decode_rid(payload.lexeme_id, "lexeme"), decode_rid(payload.sense_id, "sense")
    private = RecordID("morpheme", uuid4().hex)
    foreign = RecordID("morpheme", uuid4().hex)
    await create(job_db, private, {"text": "mine", "type": "root", "owner": a})
    await create(job_db, foreign, {"text": "secret", "type": "root", "owner": b})
    await relate(job_db, "composed_of", lexeme, private, {"order": 9, "owner": a})
    await relate(job_db, "composed_of", lexeme, foreign, {"order": 10, "owner": a})
    await relate(job_db, "composed_of", lexeme, private, {"order": 11, "owner": b})
    assert len(await read_morphemes(job_db, alice, payload.lexeme_id)) == 3
    assert len(await read_morphemes(job_db, bob, payload.lexeme_id)) == 2
    group = RecordID("tag", ["morph_group", "en", "decide", "root", 1])
    await relate(job_db, "member_of", private, group, {"owner": a})
    await relate(job_db, "member_of", foreign, group, {"owner": a})
    await relate(job_db, "member_of", foreign, group, {"owner": b})
    hidden = RecordID("tag", uuid4().hex)
    await create(job_db, hidden, {"name": "hidden", "kind": "morph_group", "owner": b})
    await relate(job_db, "member_of", sense, hidden, {"owner": a})
    await relate(job_db, "member_of", private, hidden, {"owner": a})
    members = await read_group_members(job_db, alice, payload.sense_id, "sense")
    assert encode_rid(private, "morpheme") in {row.id for row in members}
    assert encode_rid(foreign, "morpheme") not in {row.id for row in members}
    with pytest.raises(AppError):
        await read_group_members(job_db, alice, encode_rid(foreign, "morpheme"), "morpheme")
    before = await visible(job_db, "composed_of", a)
    await enrich(job_db, morphology_reader, payload)
    assert await visible(job_db, "composed_of", a) == before
    private_lexeme = RecordID("lexeme", uuid4().hex)
    await create(
        job_db,
        private_lexeme,
        {"pos": "noun", "etymology_no": 1, "forms": [], "pron": [], "owner": b},
    )
    await relate(job_db, "composed_of", private_lexeme, foreign, {"order": 0, "owner": b})
    opaque = encode_rid(private_lexeme, "lexeme")
    assert len(await read_morphemes(job_db, bob, opaque)) == 1
    with pytest.raises(AppError):
        await read_morphemes(job_db, alice, opaque)


@pytest.mark.parametrize(
    "failure", ["unavailable", "rejected", "ambiguous", "identity", "order", "type", "type_order"]
)
async def test_optional_llm_rejected_or_unavailable_creates_nothing(
    job_db: AsyncWsSurrealConnection,
    morphology_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    user = await owner(job_db)
    payload = await materialized(job_db, morphology_reader, "unanalysed")
    proposal = Proposal(
        components=[
            Component(position=0, text="decide", type="root", identity=["en", "decide", "root", 1]),
            Component(position=1, text="-ion", type="suffix", identity=["en", "-ion", "suffix", 1]),
        ]
    )
    if failure == "identity":
        proposal.components[0].identity = ["en", "invented", "root", 1]
    elif failure == "order":
        proposal.components[1].position = 0
    elif failure == "type":
        proposal.components[1].type = "root"
    elif failure == "ambiguous":
        proposal.components = []
    elif failure == "type_order":
        proposal.components.reverse()
        for index, component in enumerate(proposal.components):
            component.position = index
    gateway = AsyncMock(
        side_effect=(
            LlmUnavailable("disabled")
            if failure == "unavailable"
            else LlmUnavailable("rejected_response")
            if failure == "rejected"
            else None
        ),
        return_value=LlmResult(value=proposal, cached=False),
    )
    monkeypatch.setattr("app.services.llm.generate_json", gateway)
    await enrich(job_db, morphology_reader, payload, llm_settings=Settings(), user=user)
    assert gateway.await_count == 1
    assert await visible(job_db, "morpheme", None) == []
    assert await visible(job_db, "composed_of", None) == []
    assert await visible(job_db, "member_of", None) == []
    assert await prepare_morphology(
        morphology_reader, lexeme_key("en", "conflicting", "noun"), [], proposal
    ) == ([], [])


async def test_optional_llm_validated_provenance_and_source_precedence(
    job_db: AsyncWsSurrealConnection,
    morphology_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await owner(job_db)
    proposal = Proposal(
        components=[
            Component(position=0, text="re-", type="prefix", identity=["en", "re-", "prefix", 1]),
            Component(position=1, text="decide", type="root", identity=["en", "decide", "root", 1]),
        ]
    )
    gateway = AsyncMock(return_value=LlmResult(value=proposal, cached=False))
    monkeypatch.setattr("app.services.llm.generate_json", gateway)
    payload = await materialized(job_db, morphology_reader, "unanalysed")
    await enrich(job_db, morphology_reader, payload, llm_settings=Settings(), user=user)
    parts = await read_morphemes(job_db, user, payload.lexeme_id)
    assert [part.source for part in parts] == ["llm:morphology-v1"] * 2
    source = await materialized(job_db, morphology_reader, "decision")
    await enrich(job_db, morphology_reader, source, llm_settings=Settings(), user=user)
    conflicting = await materialized(job_db, morphology_reader, "conflicting")
    await enrich(job_db, morphology_reader, conflicting, llm_settings=Settings(), user=user)
    assert gateway.await_count == 1
    assert gateway.call_args.kwargs["shared_sources"] == (
        RecordID("lexeme", cast(DictionaryKey, decode_rid(payload.lexeme_id, "lexeme").id)),
    )


async def test_existing_shared_composition_is_never_replaced_or_mixed(
    job_db: AsyncWsSurrealConnection, morphology_reader: LexiconReader
) -> None:
    payload = await materialized(job_db, morphology_reader, "unanalysed")
    lexeme = decode_rid(payload.lexeme_id, "lexeme")
    morpheme = RecordID("morpheme", ["en", "decide", "root", 1])
    await create(job_db, morpheme, {"text": "decide", "type": "root"})
    await relate(job_db, "composed_of", lexeme, morpheme, {"order": 7, "source": "wiktionary"})
    from app.db.dictionary_materialize import materialize
    from app.db.dictionary_source import Materialization

    proposal = Proposal(
        components=[
            Component(position=0, text="re-", type="prefix", identity=["en", "re-", "prefix", 1]),
            Component(position=1, text="decide", type="root", identity=["en", "decide", "root", 1]),
        ]
    )
    rows, edges = await prepare_morphology(
        morphology_reader, cast(DictionaryKey, lexeme.id), [], proposal
    )
    with pytest.raises(AppError, match="conflicts"):
        await materialize(
            job_db,
            Materialization(decode_rid(payload.lemma_id, "lemma"), [lexeme], [], rows, edges),
        )
    assert len(await visible(job_db, "composed_of", None)) == 1
    assert await visible(job_db, "tag", None) == []
