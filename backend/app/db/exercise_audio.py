"""Resolve the canonical spelling represented by lexeme pronunciation recordings."""

from surrealdb import AsyncSurrealConnection

from app.core.record_ids import decode_rid
from app.db.auth import _rows
from app.db.srs import user_record
from app.domain.exercises import ExerciseContext


async def headword(db: AsyncSurrealConnection, context: ExerciseContext) -> str | None:
    rows = await _rows(
        db,
        "SELECT text FROM $lemma WHERE owner = NONE OR owner = $user;",
        {"lemma": decode_rid(context.lemma.id, "lemma"), "user": user_record(context.owner)},
    )
    return rows[0]["text"] if rows else None
