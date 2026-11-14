from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.dictionary import DictionaryTable
from app.domain.notes import NoteCreate, NoteRead, NoteUpdate
from app.services import notes

router = APIRouter(prefix="/api/notes", tags=["notes"])
Actor = Annotated[User, Depends(current_user)]


@router.post("", status_code=201)
async def create_note(data: NoteCreate, db: Db, actor: Actor, response: Response) -> NoteRead:
    response.headers["Cache-Control"] = "no-store"
    return await notes.create(db, actor.id, data)


@router.get("")
async def list_notes(
    target_table: DictionaryTable, target_id: str, db: Db, actor: Actor, response: Response
) -> list[NoteRead]:
    response.headers["Cache-Control"] = "no-store"
    return await notes.list_notes(db, actor.id, target_table, target_id)


@router.get("/{id}")
async def read_note(id: str, db: Db, actor: Actor, response: Response) -> NoteRead:
    response.headers["Cache-Control"] = "no-store"
    return await notes.read(db, actor.id, id)


@router.patch("/{id}")
async def update_note(
    id: str, data: NoteUpdate, db: Db, actor: Actor, response: Response
) -> NoteRead:
    response.headers["Cache-Control"] = "no-store"
    return await notes.update(db, actor.id, id, data)


@router.delete("/{id}", status_code=204)
async def delete_note(id: str, db: Db, actor: Actor) -> Response:
    await notes.delete(db, actor.id, id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
