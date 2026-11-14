from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.config import Settings
from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_enrichment_test_support import clear_edges, reset_metadata
from app.db.dictionary_schema_test_support import create, relate, visible
from app.db.jobs_test_support import make_due, worker_read
from app.domain.add_to_project import EnrichJobPayload
from app.domain.auth import UserCreate
from app.domain.dictionary_keys import DictionaryKey, lemma_key, sense_key
from app.domain.identity import user_key
from app.domain.jobs import Job, JobCreate
from app.services import jobs
from app.services.auth import create_user
from app.services.dictionary import materialize_lemma, read_record
from app.services.lexicon import LexiconReader
from app.worker.context import get_context
from app.worker.handlers import HANDLERS
from app.worker.runtime import run_once

pytestmark = pytest.mark.integration


async def enqueue(
    db: AsyncWsSurrealConnection,
    reader: LexiconReader,
    word: str,
    *,
    owner: str | None = None,
    selected: list[DictionaryKey] | None = None,
) -> Job:
    if word == "run" and selected is None:
        selected = [sense_key("en", "run", "verb", source_sense_id="run-move")]
    result = await materialize_lemma(db, reader, word, selected_senses=selected)
    sense_id = result.selected_sense_ids[0]
    sense = decode_rid(sense_id, "sense")
    lexeme_id = next(
        rid
        for rid in result.lexeme_ids
        if decode_rid(rid, "lexeme").id == cast(DictionaryKey, sense.id)[:4]
    )
    payload = EnrichJobPayload(
        lemma_key=lemma_key("en", word),
        lemma_id=result.lemma_id,
        lexeme_id=lexeme_id,
        sense_id=sense_id,
    )
    return await jobs.enqueue(
        db, JobCreate(type="enrich", owner=owner, payload=payload.model_dump())
    )


def configured(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"lexicon_path": Path(__file__).parents[1] / "fixtures" / "lexicon_small.sqlite"}
    )


async def test_registered_dispatch_relations_metadata_repeat_and_overrides(
    job_db: AsyncWsSurrealConnection, job_settings: Settings, lexicon_reader: LexiconReader
) -> None:
    alice = await create_user(
        job_db, UserCreate(username=f"enrich_{uuid4().hex}", password="test-password")
    )
    bob = await create_user(
        job_db, UserCreate(username=f"enrich_{uuid4().hex}", password="test-password")
    )
    alice_id, bob_id = RecordID("user", user_key(alice.id)), RecordID("user", user_key(bob.id))
    job = await enqueue(job_db, lexicon_reader, "run", owner=alice.id)
    payload = EnrichJobPayload.model_validate(job.payload)
    lemma = decode_rid(payload.lemma_id, "lemma")
    await reset_metadata(job_db, lemma, {"freq_zipf": 0, "exam_tags": []})
    await create(
        job_db,
        RecordID("override", [alice_id, lemma]),
        {
            "owner": alice_id,
            "fields": {"freq_zipf": 9.9, "exam_tags": ["personal"]},
            "updated_at": datetime.now(UTC),
        },
    )
    assert HANDLERS["enrich"].__module__ == "app.worker.enrich"
    assert await run_once(job_db, settings=configured(job_settings))
    assert (await worker_read(job_db, job)).status == "done"
    assert await visible(job_db, "relates_to", alice_id) == []
    assert [row["id"] for row in await visible(job_db, "sense", alice_id)] == [
        decode_rid(payload.sense_id, "sense")
    ]

    await materialize_lemma(job_db, lexicon_reader, "move")
    await clear_edges(job_db)
    user_edge = await relate(
        job_db,
        "relates_to",
        decode_rid(payload.sense_id, "sense"),
        RecordID("sense", ["en", "move", "verb", 1, "move-position"]),
        {"type": "confusable", "source": "user", "owner": bob_id},
    )
    repeat = await enqueue(job_db, lexicon_reader, "run", owner=bob.id)
    await clear_edges(job_db)
    assert await run_once(job_db, settings=configured(job_settings))
    assert (await worker_read(job_db, repeat)).status == "done"
    shared = await read_record(job_db, bob.id, payload.lemma_id, "lemma")
    effective = await read_record(job_db, alice.id, payload.lemma_id, "lemma")
    assert shared is not None and effective is not None
    assert shared.owner is None and shared.fields["freq_zipf"] == 5.4
    assert shared.fields["exam_tags"] == ["cet4", "cet6"]
    assert shared.fields["exam_tag_sources"] == [
        {"tag": "cet4", "source": "ecdict"},
        {"tag": "cet6", "source": "ecdict"},
    ]
    assert shared.fields["frequencies"] == [
        {"source": "ecdict", "bnc": 100, "coca": 120},
        {"source": "wordfreq", "zipf": 5.4},
    ]
    assert effective.fields["freq_zipf"] == 9.9 and effective.fields["exam_tags"] == ["personal"]
    edges = await visible(job_db, "relates_to", alice_id)
    assert {(edge["type"], edge["source"]) for edge in edges} == {
        ("hypernym", "oewn"),
        ("hyponym", "oewn"),
    }
    assert all(edge.get("owner") is None for edge in edges)
    assert user_edge in await visible(job_db, "relates_to", bob_id)
    before = {
        table: await visible(job_db, table, bob_id)
        for table in ("lemma", "sense", "relates_to", "override")
    }
    repeated = await enqueue(job_db, lexicon_reader, "run", owner=alice.id)
    assert await run_once(job_db, settings=configured(job_settings))
    assert (await worker_read(job_db, repeated)).status == "done"
    assert {table: await visible(job_db, table, bob_id) for table in before} == before
    with pytest.raises(RuntimeError, match="dispatch"):
        get_context()


@pytest.mark.parametrize("base_first", [True, False])
async def test_derivation_direction_provenance_and_already_materialized_only(
    job_db: AsyncWsSurrealConnection,
    job_settings: Settings,
    lexicon_reader: LexiconReader,
    base_first: bool,
) -> None:
    first, second = ("decide", "decision") if base_first else ("decision", "decide")
    job = await enqueue(job_db, lexicon_reader, first)
    assert await run_once(job_db, settings=configured(job_settings))
    assert (await worker_read(job_db, job)).status == "done"
    assert await visible(job_db, "derives_to", RecordID("user", "unused")) == []
    job = await enqueue(job_db, lexicon_reader, second)
    assert await run_once(job_db, settings=configured(job_settings))
    edges = await visible(job_db, "derives_to", RecordID("user", "unused"))
    assert len(edges) == 1
    assert edges[0]["in"] == RecordID("lexeme", ["en", "decide", "verb", 1])
    assert edges[0]["out"] == RecordID("lexeme", ["en", "decision", "noun", 1])
    assert edges[0]["source"] == "wiktionary" and edges[0]["via"] == "-ion"
    assert edges[0].get("owner") is None


async def test_registered_handler_retries_missing_artifact_then_succeeds(
    job_db: AsyncWsSurrealConnection, job_settings: Settings, lexicon_reader: LexiconReader
) -> None:
    job = await enqueue(job_db, lexicon_reader, "cat")
    bad = job_settings.model_copy(
        update={"lexicon_path": Path(__file__).with_name("missing.sqlite")}
    )
    assert await run_once(job_db, settings=bad)
    failed = await worker_read(job_db, job)
    assert failed.status == "queued" and failed.attempts == 1
    assert failed.run_after > job.run_after
    await make_due(job_db, failed)
    assert await run_once(job_db, settings=configured(job_settings))
    completed = await worker_read(job_db, job)
    assert completed.status == "done" and completed.attempts == 2


async def test_optional_absence_keeps_existing_metadata_and_logs(
    job_db: AsyncWsSurrealConnection,
    job_settings: Settings,
    lexicon_reader: LexiconReader,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.build_lexicon import build

    job = await enqueue(job_db, lexicon_reader, "cat")
    payload = EnrichJobPayload.model_validate(job.payload)
    lemma = decode_rid(payload.lemma_id, "lemma")
    await reset_metadata(job_db, lemma, {"freq_zipf": 3.2, "exam_tags": ["existing"]})
    artifact = Path.cwd() / f".enrichment-test-{uuid4().hex}.sqlite"
    try:
        build(Path(__file__).parents[1] / "fixtures" / "lexicon-small.jsonl", artifact)
        reader = LexiconReader(artifact)
        assert await reader.frequencies(payload.lemma_key) == []
        assert await reader.tags(payload.lemma_key) == []
        assert await run_once(
            job_db, settings=job_settings.model_copy(update={"lexicon_path": artifact})
        )
    finally:
        artifact.unlink(missing_ok=True)
    assert (await worker_read(job_db, job)).status == "done"
    row = next(
        row
        for row in await visible(job_db, "lemma", RecordID("user", "unused"))
        if row["id"] == lemma
    )
    assert row["freq_zipf"] == 3.2 and row["exam_tags"] == ["existing"]
    assert "enrich_optional_source_absent" in capsys.readouterr().out


async def test_private_relation_endpoint_is_not_enriched(
    job_db: AsyncWsSurrealConnection, job_settings: Settings, lexicon_reader: LexiconReader
) -> None:
    bob = await create_user(
        job_db, UserCreate(username=f"enrich_{uuid4().hex}", password="test-password")
    )
    bob_id = RecordID("user", user_key(bob.id))
    job = await enqueue(job_db, lexicon_reader, "run")
    target = RecordID("sense", ["en", "move", "verb", 1, "move-position"])
    source = next(row for row in await visible(job_db, "sense", bob_id))
    await create(
        job_db,
        target,
        {**cast(dict[str, Value], {k: v for k, v in source.items() if k != "id"}), "owner": bob_id},
    )
    assert await run_once(job_db, settings=configured(job_settings))
    assert (await worker_read(job_db, job)).status == "done"
    assert await visible(job_db, "relates_to", bob_id) == []


async def test_mismatched_payload_cannot_update_another_shared_item(
    job_db: AsyncWsSurrealConnection, job_settings: Settings, lexicon_reader: LexiconReader
) -> None:
    job = await enqueue(job_db, lexicon_reader, "run")
    assert await run_once(job_db, settings=configured(job_settings))
    before = await visible(job_db, "lemma", RecordID("user", "unused"))
    malformed = await jobs.enqueue(
        job_db,
        JobCreate(
            type="enrich",
            payload={
                **job.payload,
                "lemma_id": encode_rid(RecordID("lemma", ["en", "move"]), "lemma"),
            },
        ),
    )
    assert await run_once(job_db, settings=configured(job_settings))
    assert (await worker_read(job_db, malformed)).status == "queued"
    assert await visible(job_db, "lemma", RecordID("user", "unused")) == before
