from typing import Literal

from surrealdb import AsyncSurrealConnection

from app.core.errors import AppError
from app.db import overrides as repository
from app.domain.dictionary import DictionaryTable
from app.domain.overrides import EDITABLE_FIELDS, OverrideRead, OverrideUpdate
from app.services.user_dictionary import target_id


async def read(
    db: AsyncSurrealConnection, owner: str, table: DictionaryTable, id: str
) -> OverrideRead:
    result = await repository.manage(db, owner, target_id(table, id), action="get")
    assert result is not None
    return result


async def write(
    db: AsyncSurrealConnection,
    owner: str,
    table: DictionaryTable,
    id: str,
    data: OverrideUpdate,
    *,
    action: Literal["put", "patch"],
) -> OverrideRead:
    target = target_id(table, id)
    fields = data.fields.model_dump(include=data.fields.model_fields_set)
    if fields.keys() - EDITABLE_FIELDS[table]:
        raise AppError("override.invalid_fields", 422, "Fields are not editable on this target.")
    result = await repository.manage(db, owner, target, action=action, fields=fields)
    assert result is not None
    return result


async def reset(db: AsyncSurrealConnection, owner: str, table: DictionaryTable, id: str) -> None:
    await repository.manage(db, owner, target_id(table, id), action="delete")
