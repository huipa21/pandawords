from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.srs_optimization import OptimizationRead
from app.services import srs_optimization

router = APIRouter(prefix="/api/srs/optimization", tags=["srs"])
Actor = Annotated[User, Depends(current_user)]


@router.get("")
async def read(db: Db, actor: Actor, response: Response) -> OptimizationRead:
    response.headers["Cache-Control"] = "no-store"
    return await srs_optimization.read(db, actor.id)


@router.post("", status_code=202)
async def request(db: Db, actor: Actor, response: Response) -> OptimizationRead:
    response.headers["Cache-Control"] = "no-store"
    await srs_optimization.request(db, actor.id)
    return await srs_optimization.read(db, actor.id)
