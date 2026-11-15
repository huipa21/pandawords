from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import relations
from app.domain.relations import RelationCreate, RelationRead, RelationResult


def _id(value: str, table: str) -> RecordID:
    try:
        return decode_rid(value, table)
    except ValueError:
        raise AppError("relation.invalid_id", 422, "Invalid relation or sense ID.") from None


async def create(db: AsyncSurrealConnection, owner: str, data: RelationCreate) -> RelationResult:
    start, end = _id(data.start, "sense"), _id(data.end, "sense")
    if start == end:
        raise AppError("relation.self_link", 422, "Semantic relations require distinct senses.")
    return await relations.create(db, owner, start, end, data.type)


async def list_relations(
    db: AsyncSurrealConnection, owner: str, sense_id: str, page: int, page_size: int
) -> list[RelationRead]:
    return await relations.list_relations(db, owner, _id(sense_id, "sense"), page, page_size)


async def delete(db: AsyncSurrealConnection, owner: str, edge_id: str) -> None:
    await relations.delete(db, owner, _id(edge_id, "relates_to"))
