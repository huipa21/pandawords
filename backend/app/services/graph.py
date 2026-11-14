"""Validate graph identity before entering the repository snapshot."""

from typing import get_args

from surrealdb import AsyncSurrealConnection

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import graph
from app.domain.dictionary import DictionaryTable
from app.domain.graph import GraphQuery, GraphRead


async def read(db: AsyncSurrealConnection, owner: str, query: GraphQuery) -> GraphRead:
    try:
        focus = next(
            decode_rid(query.focus_id, table)
            for table in get_args(DictionaryTable.__value__)
            if _matches(query.focus_id, table)
        )
    except ValueError, StopIteration:
        raise AppError("graph.invalid_id", 422, "Invalid graph focus ID.") from None
    return await graph.read(db, owner, focus, query)


def _matches(value: str, table: str) -> bool:
    try:
        decode_rid(value, table)
        return True
    except ValueError:
        return False
