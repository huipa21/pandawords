"""Resolve a visible selected sense to its own effective lexeme and headword."""

from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.dictionary import _record
from app.db.project_tree import _children, _hidden, _memberships
from app.db.srs import eligible_project, user_record
from app.domain.exercises import ExerciseContext


async def selected_context(
    db: AsyncSurrealConnection,
    owner: str,
    project: RecordID,
    sense: RecordID,
    txn: UUID,
) -> ExerciseContext:
    await eligible_project(db, owner, project, sense, txn)
    user = user_record(owner)
    memberships = await _memberships(db, user, project, txn)
    hidden = _hidden(memberships)
    # Deterministic even for a legacy graph with more than one accessible ancestry.
    for lemma_id in sorted(
        {row["out"] for row in memberships if row["out"].table_name == "lemma"}, key=str
    ):
        if hidden[encode_rid(lemma_id, "lemma")]:
            continue
        edges = await _children(db, user, lemma_id, "has_lexeme", None, txn)
        for lexeme_id in sorted({row["out"] for row in edges}, key=str):
            if hidden.get(encode_rid(lexeme_id, "lexeme"), False):
                continue
            if not await _children(db, user, lexeme_id, "has_sense", [sense], txn):
                continue
            lemma = await _record(db, user, lemma_id, txn)
            lexeme = await _record(db, user, lexeme_id, txn)
            selected = await _record(db, user, sense, txn)
            if lemma is not None and lexeme is not None and selected is not None:
                return ExerciseContext(
                    owner=owner,
                    project_id=encode_rid(project, "project"),
                    sense_id=encode_rid(sense, "sense"),
                    lemma=lemma,
                    lexeme=lexeme,
                    sense=selected,
                    forms=(),
                )
    raise AppError("exercise.not_eligible", 409, "Selected lexeme is unavailable.")
