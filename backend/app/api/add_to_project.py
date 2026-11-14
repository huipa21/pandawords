from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import Db, current_user, get_lexicon_reader
from app.domain.add_to_project import AddToProjectCreate, AddToProjectRead
from app.domain.auth import User
from app.services.add_to_project import add_to_project
from app.services.lexicon import LexiconReader

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/{id}/dictionary", response_model=AddToProjectRead)
async def add_dictionary_candidate(
    id: str,
    body: AddToProjectCreate,
    db: Db,
    actor: Annotated[User, Depends(current_user)],
    reader: Annotated[LexiconReader, Depends(get_lexicon_reader)],
    response: Response,
) -> AddToProjectRead:
    response.headers["Cache-Control"] = "no-store"
    return await add_to_project(db, reader, actor.id, id, body)
