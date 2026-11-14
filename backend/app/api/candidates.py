from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import current_user, get_lexicon_reader
from app.domain.candidates import CandidateRequest, CandidateResponse
from app.services.candidates import CandidateService
from app.services.lexicon import LexiconReader

router = APIRouter(
    prefix="/api/dictionary", tags=["dictionary"], dependencies=[Depends(current_user)]
)


@router.post("/candidates", response_model=CandidateResponse)
async def candidates(
    body: CandidateRequest,
    response: Response,
    reader: Annotated[LexiconReader, Depends(get_lexicon_reader)],
) -> CandidateResponse:
    response.headers["Cache-Control"] = "no-store"
    return await CandidateService(reader).resolve(body)
