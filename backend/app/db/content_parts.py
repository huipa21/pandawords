"""Manual ordered associations between two owner-private content endpoints."""

from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError
from app.db.auth import _atomic, _rows
from app.db.content import actor, identity, owned


async def assign(
    db: AsyncSurrealConnection,
    owner: str,
    passage: RecordID,
    sentence: RecordID,
    order: int,
    expected_text: str,
    expected_passage: str,
) -> None:
    user = actor(owner)

    async def operation(txn: UUID) -> None:
        parent = await owned(db, user, passage, txn)
        child = await owned(db, user, sentence, txn)
        if parent["text"] != expected_passage:
            raise AppError("content.changed", 409, "Passage changed during assignment.")
        if child["text"] != expected_text or child["lang"] != parent["lang"]:
            raise AppError("content.invalid_part", 422, "Sentence must match the original segment.")
        await _rows(
            db,
            "DELETE part_of WHERE owner = $user AND out = $passage AND order = $order;",
            {"user": user, "passage": passage, "order": order},
            txn_id=txn,
        )
        await _rows(
            db,
            "RELATE $sentence->$edge->$passage CONTENT $fields;",
            {
                "sentence": sentence,
                "edge": identity("part_of", owner, sentence, passage, order),
                "passage": passage,
                "fields": {"owner": user, "order": order},
            },
            txn_id=txn,
        )

    await _atomic(db, operation)


async def remove(
    db: AsyncSurrealConnection,
    owner: str,
    passage: RecordID,
    order: int,
) -> None:
    user = actor(owner)

    async def operation(txn: UUID) -> None:
        await owned(db, user, passage, txn)
        rows = await _rows(
            db,
            "SELECT * FROM part_of WHERE owner = $user AND out = $passage "
            "AND order = $order LIMIT 1;",
            {"user": user, "passage": passage, "order": order},
            txn_id=txn,
        )
        if not rows:
            raise AppError("content.not_found", 404, "Association not found.")
        await owned(db, user, rows[0]["in"], txn)
        await _rows(
            db,
            "DELETE $edge WHERE owner = $user;",
            {"edge": rows[0]["id"], "user": user},
            txn_id=txn,
        )

    await _atomic(db, operation)
