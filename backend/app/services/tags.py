from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import tags as repository
from app.domain.tags import TagAssignmentRead, TagCreate, TagRead, TagTarget, TagUpdate


def _id(table: TagTarget, value: str) -> RecordID:
    try:
        return decode_rid(value, table)
    except ValueError:
        raise AppError("dictionary.not_found", 404, "Dictionary item not found.") from None


async def create(db: AsyncSurrealConnection, owner: str, data: TagCreate) -> TagRead:
    return await repository.create(db, owner, data)


async def list_tags(db: AsyncSurrealConnection, owner: str) -> list[TagRead]:
    return await repository.list_tags(db, owner)


async def read(db: AsyncSurrealConnection, owner: str, id: str) -> TagRead:
    result = await repository.manage(db, owner, _id("tag", id), "get")
    assert result is not None
    return result


async def update(db: AsyncSurrealConnection, owner: str, id: str, data: TagUpdate) -> TagRead:
    result = await repository.manage(db, owner, _id("tag", id), "patch", data)
    assert result is not None
    return result


async def delete(db: AsyncSurrealConnection, owner: str, id: str) -> None:
    await repository.manage(db, owner, _id("tag", id), "delete")


async def memberships(
    db: AsyncSurrealConnection,
    owner: str,
    table: TagTarget,
    id: str,
) -> list[TagAssignmentRead]:
    return await repository.memberships(db, owner, _id(table, id))


async def assign(
    db: AsyncSurrealConnection,
    owner: str,
    id: str,
    table: TagTarget,
    target_id: str,
    *,
    remove: bool = False,
) -> None:
    await repository.assign(db, owner, _id("tag", id), _id(table, target_id), remove=remove)
