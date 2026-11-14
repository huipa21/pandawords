"""Atomic, insert-only shared graph materialization."""

from typing import cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.db.dictionary_source import Materialization
from app.domain.dictionary import MaterializedDictionary


async def shared_exists(
    db: AsyncSurrealConnection, record: RecordID, txn: UUID, *, conflict: bool = True
) -> bool:
    rows = await _rows(
        db, "SELECT id FROM $record WHERE owner = NONE;", {"record": record}, txn_id=txn
    )
    if rows:
        return True
    if conflict:
        existence = await _rows(
            db, "RETURN [{exists: record::exists($record)}];", {"record": record}, txn_id=txn
        )
        if existence[0]["exists"]:
            raise AppError(
                "dictionary.identity_conflict",
                409,
                "Shared dictionary identity is occupied by user content.",
            )
    return False


async def materialize(
    db: AsyncSurrealConnection,
    plan: Materialization,
    *,
    txn_id: UUID | None = None,
    skip_private_endpoints: bool = False,
) -> MaterializedDictionary:
    async def operation(txn: UUID) -> MaterializedDictionary:
        compositions = {}
        for edge in plan.edges:
            if edge.table == "composed_of":
                compositions.setdefault(str(edge.start), (edge.start, set()))[1].add(
                    (str(edge.end), edge.fields["order"], edge.fields.get("source"))
                )
        for lexeme, expected in compositions.values():
            existing = await _rows(
                db,
                "SELECT out, order, source FROM composed_of WHERE in = $lexeme AND owner = NONE;",
                {"lexeme": lexeme},
                txn_id=txn,
            )
            actual = {(str(row["out"]), row["order"], row.get("source")) for row in existing}
            if actual and actual != expected:
                raise AppError(
                    "dictionary.morphology_conflict",
                    409,
                    "Existing shared morphology conflicts with this analysis.",
                )
        for row in plan.rows:
            if not await shared_exists(db, row.record, txn):
                await _rows(
                    db,
                    "CREATE $record CONTENT $fields;",
                    {"record": row.record, "fields": cast(Value, {**row.fields, "owner": None})},
                    txn_id=txn,
                )
        for edge in plan.edges:
            # Semantic targets are connected only after both selected endpoints exist.
            if not await shared_exists(
                db, edge.start, txn, conflict=not skip_private_endpoints
            ) or not await shared_exists(db, edge.end, txn, conflict=not skip_private_endpoints):
                continue
            if not await shared_exists(db, edge.record, txn):
                await _rows(
                    db,
                    "RELATE $start->$edge->$end CONTENT $fields;",
                    {
                        "start": edge.start,
                        "edge": edge.record,
                        "end": edge.end,
                        "fields": cast(Value, {**edge.fields, "owner": None}),
                    },
                    txn_id=txn,
                )
        return MaterializedDictionary(
            lemma_id=encode_rid(plan.lemma, "lemma"),
            lexeme_ids=[encode_rid(record, "lexeme") for record in plan.lexemes],
            selected_sense_ids=[encode_rid(record, "sense") for record in plan.senses],
        )

    return await operation(txn_id) if txn_id is not None else await _atomic(db, operation)
