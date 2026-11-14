"""Owner-private content and transactional associations."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.domain.content import ContentCreate, ContentKind, ContentRead
from app.domain.identity import user_key


def identity(table: str, *values: object) -> RecordID:
    digest = hashlib.sha256(
        json.dumps(values, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()
    return RecordID(table, digest)


def actor(owner: str) -> RecordID:
    return RecordID("user", user_key(owner))


def read(row: dict[str, Any]) -> ContentRead:
    return ContentRead(
        id=encode_rid(row["id"], row["id"].table_name),
        kind=row["id"].table_name,
        **{
            key: row[key]
            for key in ("text", "lang", "source", "title", "translation")
            if key in row
        },
    )


async def owned(
    db: AsyncSurrealConnection, user: RecordID, target: RecordID, txn: UUID | None = None
) -> dict[str, Any]:
    rows = await _rows(
        db,
        "SELECT * FROM $target WHERE owner = $user;",
        {"target": target, "user": user},
        txn_id=txn,
    )
    if not rows:
        raise AppError("content.not_found", 404, "Content not found.")
    return rows[0]


async def insert(
    db: AsyncSurrealConnection, user: RecordID, target: RecordID, data: ContentCreate, txn: UUID
) -> ContentRead:
    fields = data.model_dump(
        exclude={"title"} if target.table_name == "sentence" else {"translation"}
    )
    rows = await _rows(
        db,
        "CREATE $target CONTENT $fields RETURN AFTER;",
        {"target": target, "fields": cast(Value, {**fields, "owner": user})},
        txn_id=txn,
    )
    return read(rows[0])


async def create(
    db: AsyncSurrealConnection, owner: str, kind: ContentKind, data: ContentCreate
) -> ContentRead:
    async def operation(txn: UUID) -> ContentRead:
        return await insert(db, actor(owner), RecordID(kind, uuid4().hex), data, txn)

    return await _atomic(db, operation)


async def list_content(
    db: AsyncSurrealConnection, owner: str, kind: ContentKind, limit: int, offset: int
) -> list[ContentRead]:
    rows = await _rows(
        db,
        "SELECT * FROM type::table($table) WHERE owner = $user "
        "ORDER BY id LIMIT $limit START $offset;",
        {"table": kind, "user": actor(owner), "limit": limit, "offset": offset},
    )
    return [read(row) for row in rows]


async def remove_edges(
    db: AsyncSurrealConnection, user: RecordID, target: RecordID, txn: UUID
) -> None:
    await _rows(
        db,
        "DELETE part_of WHERE owner = $user AND (in = $target OR out = $target);",
        {"user": user, "target": target},
        txn_id=txn,
    )
    await _rows(
        db,
        "DELETE used_in WHERE owner = $user AND out = $target;",
        {"user": user, "target": target},
        txn_id=txn,
    )


async def manage(
    db: AsyncSurrealConnection,
    owner: str,
    target: RecordID,
    data: ContentCreate | None = None,
    *,
    delete: bool = False,
) -> ContentRead | None:
    async def operation(txn: UUID) -> ContentRead | None:
        row = await owned(db, actor(owner), target, txn)
        if delete:
            for table in ("part_of", "used_in"):
                foreign = await _rows(
                    db,
                    "SELECT id FROM type::table($table) WHERE (in = $target OR out = $target) "
                    "AND (owner = NONE OR owner != $user) LIMIT 1;",
                    {"table": table, "target": target, "user": actor(owner)},
                    txn_id=txn,
                )
                if foreign:
                    # SurrealDB automatically cascades even foreign-owned graph edges.
                    raise AppError(
                        "content.foreign_associations",
                        409,
                        "Content has protected foreign associations.",
                    )
        if delete or data is not None:
            await remove_edges(db, actor(owner), target, txn)
            if data is not None:
                fields = data.model_dump(
                    exclude={"title"} if target.table_name == "sentence" else {"translation"}
                )
                rows = await _rows(
                    db,
                    "UPDATE $target MERGE $fields WHERE owner = $user RETURN AFTER;",
                    {"target": target, "user": actor(owner), "fields": fields},
                    txn_id=txn,
                )
                return read(rows[0])
            await _rows(
                db,
                "DELETE $target WHERE owner = $user;",
                {"target": target, "user": actor(owner)},
                txn_id=txn,
            )
            return None
        return read(row)

    return await _atomic(db, operation)


async def ingest(
    db: AsyncSurrealConnection,
    owner: str,
    data: ContentCreate,
    parts: list[ContentCreate],
    link: Callable[[RecordID, int, UUID], Awaitable[None]],
) -> RecordID:
    user = actor(owner)
    passage = identity("passage", owner, data.model_dump(exclude={"translation"}))

    async def operation(txn: UUID) -> RecordID:
        existing = await _rows(
            db,
            "SELECT * FROM $target WHERE owner = $user;",
            {"target": passage, "user": user},
            txn_id=txn,
        )
        if existing:
            if any(
                existing[0].get(key) != value
                for key, value in data.model_dump(exclude={"translation"}).items()
            ):
                raise AppError("content.retry_conflict", 409, "Passage was edited.")
            # Editing a deterministic sentence invalidates a previous ingestion.
            # Rebuild its ordered associations on retry using the original input.
            await remove_edges(db, user, passage, txn)
        else:
            await insert(db, user, passage, data, txn)
        for order, part in enumerate(parts):
            sentence = identity("sentence", owner, part.model_dump(exclude={"title"}))
            found = await _rows(
                db,
                "SELECT * FROM $target WHERE owner = $user;",
                {"target": sentence, "user": user},
                txn_id=txn,
            )
            if not found:
                await insert(db, user, sentence, part, txn)
            elif any(
                found[0].get(key) != value
                for key, value in part.model_dump(exclude={"title"}).items()
            ):
                raise AppError("content.retry_conflict", 409, "Reused sentence was edited.")
            await _rows(
                db,
                "RELATE $sentence->$edge->$passage CONTENT $fields;",
                {
                    "sentence": sentence,
                    "passage": passage,
                    "edge": identity("part_of", owner, sentence, passage, order),
                    "fields": {"owner": user, "order": order},
                },
                txn_id=txn,
            )
            await link(sentence, order, txn)
        return passage

    return await _atomic(db, operation)


async def parts(db: AsyncSurrealConnection, owner: str, passage: RecordID) -> list[dict[str, Any]]:
    user = actor(owner)
    await owned(db, user, passage)
    edges = await _rows(
        db,
        "SELECT * FROM part_of WHERE owner = $user AND out = $passage ORDER BY order LIMIT 201;",
        {"user": user, "passage": passage},
    )
    if len(edges) > 200:
        raise AppError("content.too_many_sentences", 422, "Passage exceeds sentence bound.")
    result = []
    for edge in edges:
        try:
            result.append({"row": await owned(db, user, edge["in"]), "order": edge["order"]})
        except AppError:
            continue
    return result


async def links(
    db: AsyncSurrealConnection, owner: str, sentence: RecordID, txn: UUID | None = None
) -> list[dict[str, Any]]:
    user = actor(owner)
    await owned(db, user, sentence, txn)
    return await _rows(
        db,
        "SELECT * FROM used_in WHERE owner = $user AND out = $sentence "
        "AND in.id != NONE AND (in.owner = NONE OR in.owner = $user) LIMIT 2001;",
        {"user": user, "sentence": sentence},
        txn_id=txn,
    )


async def resolve(
    db: AsyncSurrealConnection,
    owner: str,
    sentence: RecordID,
    sense: RecordID,
    span: tuple[int, int],
    txn: UUID,
) -> str:
    user = actor(owner)
    row = await owned(db, user, sentence, txn)
    if not 0 <= span[0] < span[1] <= len(row["text"]):
        raise AppError("content.invalid_span", 422, "Invalid occurrence span.")
    visible = await _rows(
        db,
        "SELECT id FROM $sense WHERE owner = NONE OR owner = $user;",
        {"sense": sense, "user": user},
        txn_id=txn,
    )
    if not visible:
        raise AppError("content.not_found", 404, "Sense not found.")
    await _rows(
        db,
        "DELETE used_in WHERE owner = $user AND out = $sentence AND span = $span;",
        {"user": user, "sentence": sentence, "span": list(span)},
        txn_id=txn,
    )
    edge = identity("used_in", owner, sentence, span)
    await _rows(
        db,
        "RELATE $sense->$edge->$sentence CONTENT $fields;",
        {
            "sense": sense,
            "edge": edge,
            "sentence": sentence,
            "fields": {"owner": user, "span": list(span)},
        },
        txn_id=txn,
    )
    return encode_rid(edge, "used_in")


async def delete_link(
    db: AsyncSurrealConnection, owner: str, sentence: RecordID, edge: RecordID
) -> None:
    async def operation(txn: UUID) -> None:
        await owned(db, actor(owner), sentence, txn)
        rows = await links(db, owner, sentence, txn)
        if not any(row["id"] == edge for row in rows):
            raise AppError("content.not_found", 404, "Association not found.")
        await _rows(
            db,
            "DELETE $edge WHERE owner = $user AND out = $sentence;",
            {"edge": edge, "user": actor(owner), "sentence": sentence},
            txn_id=txn,
        )

    await _atomic(db, operation)
