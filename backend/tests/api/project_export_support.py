"""Real-database seed for project export tests: one exporting user plus a foreign account."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.record_ids import decode_rid
from app.db.dictionary_schema_test_support import create, relate
from app.db.project_schema_test_support import put_override
from app.domain.dictionary_keys import lexeme_key, sense_key
from app.services.dictionary import materialize_lemma
from app.services.lexicon import LexiconReader

NOW = datetime(2026, 11, 14, tzinfo=UTC)
ALICE_IMAGE = b"\x89PNG\r\n\x1a\nalice-image"
SHARED_AUDIO = b"ID3shared-audio"
BOB_IMAGE = b"\x89PNG\r\n\x1a\nBOB-SECRET-IMAGE"
CARD: dict[str, Value] = {
    "card_id": 7,
    "state": 2,
    "step": None,
    "stability": 3.5,
    "difficulty": 5.0,
    "due": NOW,
    "last_review": NOW,
}


@dataclass
class Dictionary:
    lemma: RecordID
    lexeme: RecordID
    move: RecordID
    operate: RecordID
    flow: RecordID


async def dictionary(db: AsyncWsSurrealConnection, reader: LexiconReader) -> Dictionary:
    entry = await materialize_lemma(db, reader, "run")
    flow = sense_key("en", "run", "verb", source_sense_id="run-flow")
    await materialize_lemma(db, reader, "run", selected_senses=[flow])

    def sense(name: str) -> RecordID:
        return RecordID("sense", sense_key("en", "run", "verb", source_sense_id=name))

    return Dictionary(
        lemma=decode_rid(entry.lemma_id, "lemma"),
        lexeme=RecordID("lexeme", lexeme_key("en", "run", "verb")),
        move=sense("run-move"),
        operate=sense("run-operate"),
        flow=sense("run-flow"),
    )


async def include(
    db: AsyncWsSurrealConnection,
    owner: RecordID,
    project: RecordID,
    target: RecordID,
    *,
    hidden: bool = False,
    study_order: int | None = None,
) -> None:
    fields: dict[str, Value] = {"owner": owner, "hidden": hidden, "added_at": NOW}
    if study_order is not None:
        fields["study_order"] = study_order
    await relate(db, "includes", project, target, fields)


async def owned(
    db: AsyncWsSurrealConnection, table: str, owner: RecordID, **fields: Any
) -> RecordID:
    record = RecordID(table, uuid4().hex)
    await create(db, record, {"owner": owner, **fields})
    return record


def store_file(root: Path, relative: str, content: bytes) -> str:
    path = root.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return relative


async def media(
    db: AsyncWsSurrealConnection,
    owner: RecordID | None,
    target: RecordID,
    path: str,
    kind: str = "image",
) -> RecordID:
    record = RecordID("media", uuid4().hex)
    fields: dict[str, Value] = {
        "owner": owner,
        "target": target,
        "kind": kind,
        "mime": "image/png" if kind == "image" else "audio/mpeg",
        "source": "upload" if kind == "image" else "wiktionary",
        "path": path,
    }
    if kind == "audio":
        fields["accent"] = "US"
    await create(db, record, fields)
    return record


async def progress(
    db: AsyncWsSurrealConnection,
    owner: RecordID,
    sense: RecordID,
    project: RecordID,
    attempt: str,
) -> None:
    memory = RecordID("memory", [owner, sense])
    await create(db, memory, {"owner": owner, "sense": sense, "introduced": True, **CARD})
    await create(
        db,
        RecordID("review_log", uuid4().hex),
        {
            "owner": owner,
            "memory": memory,
            "project": project,
            "exercise": "recall",
            "correct": True,
            "hint_used": False,
            "duration_ms": 1200,
            "auto_rating": 3,
            "rating": 3,
            "at": NOW,
            "is_introduction": True,
            "attempt_id": attempt,
        },
    )


async def foreign_account(
    db: AsyncWsSurrealConnection,
    words: Dictionary,
    bob: RecordID,
    project: RecordID,
    media_root: Path,
) -> None:
    """Another user's project, overlay, note, owned tag edge, media and progress on shared rows."""
    await include(db, bob, project, words.lemma)
    await include(db, bob, project, words.move)
    await include(db, bob, project, words.flow)
    await put_override(db, bob, words.move, {"definition": "BOB-SECRET-OVERRIDE"})
    await owned(db, "note", bob, target=words.move, kind="note", text="BOB-SECRET-NOTE")
    tag = await owned(db, "tag", bob, kind="custom", name="BOB-SECRET-TAG")
    await relate(db, "member_of", words.move, tag, {"owner": bob})
    sentence = await owned(
        db, "sentence", bob, text="BOB-SECRET-SENTENCE", lang="en", translation={}, source="user"
    )
    await relate(db, "used_in", words.move, sentence, {"owner": bob})
    path = store_file(media_root, "image/bb/bob.png", BOB_IMAGE)
    await media(db, bob, words.move, path)
    await progress(db, bob, words.move, project, "bob-attempt")
