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


async def materialize(db: AsyncSurrealConnection, plan: Materialization) -> MaterializedDictionary:
    async def operation(txn: UUID) -> MaterializedDictionary:
        async def shared_exists(record: RecordID) -> bool:
            rows = await _rows(
                db, "SELECT id FROM $record WHERE owner = NONE;", {"record": record}, txn_id=txn
            )
            if rows:
                return True
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

        for row in plan.rows:
            if not await shared_exists(row.record):
                await _rows(
                    db,
                    "CREATE $record CONTENT $fields;",
                    {"record": row.record, "fields": cast(Value, {**row.fields, "owner": None})},
                    txn_id=txn,
                )
        for edge in plan.edges:
            # Semantic targets are connected only after both selected endpoints exist.
            if not await shared_exists(edge.start) or not await shared_exists(edge.end):
                continue
            if not await shared_exists(edge.record):
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

    return await _atomic(db, operation)
