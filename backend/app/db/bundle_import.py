"""Transaction-scoped reads and inserts for bundle imports (project import / user restore).

Every call takes the caller's ``txn`` so a failed import rolls back as a whole. Rows carry
explicit IDs chosen by the import planner; shared rows are only inserted when the planner
found their deterministic ID free, so existing shared rows are never rewritten.
"""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.db.auth import _rows
from app.domain.bundle_import import ExistingState, ImportPlan, Row, StateQuery

_CHUNK = 500


def _chunks[T](items: Sequence[T]) -> list[Sequence[T]]:
    return [items[start : start + _CHUNK] for start in range(0, len(items), _CHUNK)]


async def read_state(
    db: AsyncSurrealConnection, user: RecordID, query: StateQuery, txn: UUID
) -> ExistingState:
    state = ExistingState()
    for part in _chunks(list(dict.fromkeys(query.shared))):
        # Identity probe only: reveals whether an ID is taken and whether it is shared.
        rows = await _rows(
            db,
            "SELECT id, owner = NONE AS shared FROM $ids;",
            {"ids": cast(Value, part)},
            txn_id=txn,
        )
        for row in rows:
            state.shared[row["id"]] = row["shared"] is True
    for lang, text in query.lemma_keys:
        rows = await _rows(
            db,
            "SELECT id, (owner = NONE OR owner = $user) AS usable FROM lemma "
            "WHERE lang = $lang AND text = $text;",
            {"lang": lang, "text": text, "user": user},
            txn_id=txn,
        )
        if rows:
            state.lemmas[(lang, text)] = (rows[0]["id"], rows[0]["usable"] is True)
    memories = [RecordID("memory", [user, sense]) for sense in query.memories]
    for part in _chunks(memories):
        for row in await _rows(
            db,
            "SELECT sense FROM $ids WHERE owner = $user;",
            {"ids": cast(Value, part), "user": user},
            txn_id=txn,
        ):
            state.memories.add(row["sense"])
    for part in _chunks(query.attempts):
        for row in await _rows(
            db,
            "SELECT attempt_id FROM review_log WHERE owner = $user AND attempt_id IN $attempts;",
            {"attempts": cast(Value, part), "user": user},
            txn_id=txn,
        ):
            state.attempts.add(row["attempt_id"])
    overrides = [RecordID("override", [user, target]) for target in query.overrides]
    for part in _chunks(overrides):
        for row in await _rows(
            db,
            "SELECT id FROM $ids WHERE owner = $user;",
            {"ids": cast(Value, part), "user": user},
            txn_id=txn,
        ):
            state.overrides.add(row["id"].id[1])
    return state


async def _insert(db: AsyncSurrealConnection, query: str, rows: list[Row], txn: UUID) -> None:
    for part in _chunks(rows):
        await _rows(db, query, {"rows": cast(Value, list(part))}, txn_id=txn)


async def write_plan(
    db: AsyncSurrealConnection, user: RecordID, plan: ImportPlan, txn: UUID
) -> None:
    """Insert rows, then relations (ENFORCED endpoints must exist), then review logs."""
    await _insert(db, "INSERT $rows RETURN NONE;", plan.rows, txn)
    await _insert(db, "INSERT RELATION $rows RETURN NONE;", plan.edges, txn)
    await _insert(db, "INSERT $rows RETURN NONE;", plan.logs, txn)
    if plan.touches_tags:
        # Serializes with concurrent tag-hierarchy edits, as the tag repository does.
        await _rows(
            db, "UPDATE $user SET tag_revision += 1 WHERE id = $user;", {"user": user}, txn_id=txn
        )
