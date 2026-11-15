"""Transactional owner-bound relation identities and project-union authorization."""

from hashlib import sha256
from typing import Any, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.db.graph import _nodes
from app.db.graph_visibility import visible
from app.domain.identity import user_key
from app.domain.relations import RelationRead, RelationResult, RelationType


def _read(row: dict[str, Any], user: RecordID, labels: dict[str, str]) -> RelationRead:
    return RelationRead(
        id=encode_rid(row["id"], "relates_to"),
        start=encode_rid(row["in"], "sense"),
        end=encode_rid(row["out"], "sense"),
        start_label=labels.get(encode_rid(row["in"], "sense"), ""),
        end_label=labels.get(encode_rid(row["out"], "sense"), ""),
        type=row["type"],
        source=row["source"],
        readonly=row.get("owner") != user,
    )


async def _labels(
    db: AsyncSurrealConnection, user: RecordID, targets: set[RecordID], txn: UUID
) -> dict[str, str]:
    return {
        node.id: node.fields.definition
        for node in await _nodes(db, user, targets, txn)
        if node.table == "sense"
    }


def _require(authorized: set[RecordID], *targets: RecordID) -> None:
    if any(target not in authorized for target in targets):
        raise AppError("relation.not_found", 404, "Visible sense or relation not found.")


async def create(
    db: AsyncSurrealConnection,
    owner: str,
    start: RecordID,
    end: RecordID,
    kind: RelationType,
) -> RelationResult:
    user = RecordID("user", user_key(owner))
    # Ordered endpoints retain hypernym/hyponym direction. Identity includes the owner.
    key = sha256(f"{user}\0{start}\0{end}\0{kind}".encode()).hexdigest()
    edge = RecordID("relates_to", key)

    async def operation(txn: UUID) -> RelationResult:
        _require(await visible(db, user, txn), start, end)
        params: dict[str, Value] = {
            "user": user,
            "start": start,
            "end": end,
            "kind": kind,
            "edge": edge,
        }
        rows = await _rows(
            db,
            "SELECT * FROM relates_to WHERE owner = $user AND in = $start AND out = $end "
            "AND type = $kind AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) ORDER BY id LIMIT 1;",
            params,
            txn_id=txn,
        )
        if rows:
            labels = await _labels(db, user, {start, end}, txn)
            return RelationResult(relation=_read(rows[0], user, labels), created=False)
        # Never UPSERT: even an unexpected pre-existing shared/foreign identity is protected.
        if await _rows(db, "SELECT id FROM $edge;", {"edge": edge}, txn_id=txn):
            raise AppError("relation.conflict", 409, "Relation identity is already in use.")
        rows = await _rows(
            db,
            "RELATE $start->$edge->$end SET owner = $user, type = $kind, source = 'user';",
            params,
            txn_id=txn,
        )
        labels = await _labels(db, user, {start, end}, txn)
        return RelationResult(relation=_read(rows[0], user, labels), created=True)

    return await _atomic(db, operation)


async def list_relations(
    db: AsyncSurrealConnection, owner: str, sense: RecordID, page: int, page_size: int
) -> list[RelationRead]:
    async def operation(txn: UUID) -> list[RelationRead]:
        user = RecordID("user", user_key(owner))
        authorized = await visible(db, user, txn)
        _require(authorized, sense)
        rows = await _rows(
            db,
            "SELECT * FROM relates_to WHERE (in = $sense OR out = $sense) "
            "AND (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND in IN $authorized AND out IN $authorized ORDER BY id "
            "LIMIT $limit START $offset;",
            {
                "user": user,
                "sense": sense,
                "authorized": cast(Value, list(authorized)),
                "offset": (page - 1) * page_size,
                "limit": page_size,
            },
            txn_id=txn,
        )
        labels = await _labels(db, user, {row[key] for row in rows for key in ("in", "out")}, txn)
        return [_read(row, user, labels) for row in rows]

    return await _atomic(db, operation)


async def delete(db: AsyncSurrealConnection, owner: str, edge: RecordID) -> None:
    async def operation(txn: UUID) -> None:
        user = RecordID("user", user_key(owner))
        rows = await _rows(
            db,
            "SELECT * FROM $edge WHERE owner = $user "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user);",
            {"edge": edge, "user": user},
            txn_id=txn,
        )
        if not rows:
            raise AppError("relation.not_found", 404, "Visible sense or relation not found.")
        _require(await visible(db, user, txn), rows[0]["in"], rows[0]["out"])
        await _rows(
            db, "DELETE $edge WHERE owner = $user;", {"edge": edge, "user": user}, txn_id=txn
        )

    await _atomic(db, operation)
