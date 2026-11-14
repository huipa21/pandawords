from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.dictionary import DictionaryEntryRead, DictionaryRecordRead
from app.domain.user_dictionary import CustomSenseCreate
from app.services import user_dictionary

router = APIRouter(prefix="/api/dictionary", tags=["dictionary"])
Actor = Annotated[User, Depends(current_user)]


@router.get("/lemmas/{lemma_id}/entry")
async def read_entry(
    lemma_id: str, db: Db, actor: Actor, response: Response
) -> DictionaryEntryRead:
    response.headers["Cache-Control"] = "no-store"
    return await user_dictionary.read_entry(db, actor.id, lemma_id)


@router.post("/lexemes/{lexeme_id}/senses", status_code=201)
async def create_sense(
    lexeme_id: str, data: CustomSenseCreate, db: Db, actor: Actor, response: Response
) -> DictionaryRecordRead:
    response.headers["Cache-Control"] = "no-store"
    return await user_dictionary.create_sense(db, actor.id, lexeme_id, data)
