from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import notes as repository
from app.domain.dictionary import DictionaryTable
from app.domain.notes import NoteCreate, NoteRead, NoteUpdate
from app.services.user_dictionary import target_id


def _note_id(value: str) -> RecordID:
    try:
        return decode_rid(value, "note")
    except ValueError:
        raise AppError("note.not_found", 404, "Note not found.") from None


async def create(db: AsyncSurrealConnection, owner: str, data: NoteCreate) -> NoteRead:
    return await repository.create(db, owner, target_id(data.target_table, data.target_id), data)


async def list_notes(
    db: AsyncSurrealConnection, owner: str, table: DictionaryTable, id: str
) -> list[NoteRead]:
    return await repository.list_notes(db, owner, target_id(table, id))


async def read(db: AsyncSurrealConnection, owner: str, id: str) -> NoteRead:
    result = await repository.manage(db, owner, _note_id(id), action="get")
    assert result is not None
    return result


async def update(db: AsyncSurrealConnection, owner: str, id: str, data: NoteUpdate) -> NoteRead:
    result = await repository.manage(db, owner, _note_id(id), action="patch", data=data)
    assert result is not None
    return result


async def delete(db: AsyncSurrealConnection, owner: str, id: str) -> None:
    await repository.manage(db, owner, _note_id(id), action="delete")
