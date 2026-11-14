"""Shared pronunciation lookup and atomic attachment; no user-owned writes."""

from typing import Any, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.db.auth import _atomic, _rows
from app.domain.lexicon import Accent
from app.domain.media import Media


async def shared_target(db: AsyncSurrealConnection, lemma: RecordID, lexeme: RecordID) -> bool:
    rows = await _rows(
        db,
        "SELECT id FROM has_lexeme WHERE in = $lemma AND out = $lexeme "
        "AND owner = NONE AND in.owner = NONE AND out.owner = NONE;",
        {"lemma": lemma, "lexeme": lexeme},
    )
    return bool(rows)


async def cached(db: AsyncSurrealConnection, lexeme: RecordID, accent: Accent) -> list[Media]:
    rows = await _rows(
        db,
        "SELECT * FROM media WHERE target = $target AND owner = NONE "
        "AND target.owner = NONE AND kind = 'audio' AND accent = $accent;",
        {"target": lexeme, "accent": accent},
    )
    rows.sort(key=lambda row: (row["source"] != "wiktionary", str(row["id"])))
    return [Media.model_validate(row) for row in rows]


async def attach(
    db: AsyncSurrealConnection, lexeme: RecordID, accent: Accent, media: RecordID
) -> None:
    async def operation(txn: UUID) -> None:
        rows = await _rows(
            db, "SELECT pron FROM $id WHERE owner = NONE;", {"id": lexeme}, txn_id=txn
        )
        audio = await _rows(
            db,
            "SELECT id FROM $id WHERE owner = NONE AND target = $target "
            "AND kind = 'audio' AND accent = $accent;",
            {"id": media, "target": lexeme, "accent": accent},
            txn_id=txn,
        )
        if not rows or not audio:
            raise ValueError("Shared pronunciation target or media unavailable")
        pronunciations: list[dict[str, Any]] = rows[0]["pron"]
        matching = [pron for pron in pronunciations if pron["accent"] == accent]
        if not matching:
            pronunciations.append({"accent": accent, "ipa": "", "audio": media})
        else:
            for pronunciation in matching:
                pronunciation["audio"] = media
        await _rows(
            db,
            "UPDATE $id SET pron = $pron WHERE owner = NONE;",
            {"id": lexeme, "pron": cast(Value, pronunciations)},
            txn_id=txn,
        )

    await _atomic(db, operation)
