"""Atomic shared-only metadata updates and dictionary edge insertion."""

from typing import cast
from uuid import UUID

from pydantic import JsonValue
from surrealdb import AsyncSurrealConnection
from surrealdb.types import Value

from app.core.errors import AppError
from app.db.auth import _atomic, _rows
from app.db.dictionary_materialize import materialize, shared_exists
from app.db.dictionary_source import Materialization


async def apply(
    db: AsyncSurrealConnection, plan: Materialization, fields: dict[str, JsonValue]
) -> None:
    async def operation(txn: UUID) -> None:
        for record in (plan.lemma, *plan.lexemes, *plan.senses):
            if not await shared_exists(db, record, txn):
                raise AppError(
                    "dictionary.not_materialized", 409, "Enrichment item is not materialized."
                )
        await materialize(db, plan, txn_id=txn, skip_private_endpoints=True)
        if fields:
            await _rows(
                db,
                "UPDATE $record MERGE $fields WHERE owner = NONE;",
                {"record": plan.lemma, "fields": cast(Value, fields)},
                txn_id=txn,
            )

    await _atomic(db, operation)
