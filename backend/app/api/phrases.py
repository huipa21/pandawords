from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import Db, current_user, get_lexicon_reader
from app.domain.auth import User
from app.domain.phrases import ContainingPhrasesRead
from app.services import phrases
from app.services.lexicon import LexiconReader

router = APIRouter(prefix="/api/dictionary", tags=["dictionary"])


@router.get("/{table}/{id}/phrases", response_model=ContainingPhrasesRead)
async def containing_phrases(
    table: Literal["lemma", "lexeme"],
    id: str,
    db: Db,
    actor: Annotated[User, Depends(current_user)],
    reader: Annotated[LexiconReader, Depends(get_lexicon_reader)],
    response: Response,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ContainingPhrasesRead:
    response.headers["Cache-Control"] = "no-store"
    return await phrases.containing_phrases(
        db, reader, actor.id, table, id, offset=offset, limit=limit
    )
