from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.study_plan import DashboardRead, SenseOrderRead, SenseOrderUpdate, StudyPlanRead
from app.services import study_plan

router = APIRouter(tags=["study-plan"])
Actor = Annotated[User, Depends(current_user)]


@router.get("/api/projects/{id}/study-plan")
async def read_plan(
    id: str,
    db: Db,
    actor: Actor,
    response: Response,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> StudyPlanRead:
    response.headers["Cache-Control"] = "no-store"
    return await study_plan.read_plan(db, actor.id, id, offset=offset, limit=limit)


@router.put("/api/projects/{id}/study-plan/order")
async def reorder(
    id: str, data: SenseOrderUpdate, db: Db, actor: Actor, response: Response
) -> SenseOrderRead:
    response.headers["Cache-Control"] = "no-store"
    return await study_plan.reorder(db, actor.id, id, data)


@router.get("/api/dashboard")
async def read_dashboard(db: Db, actor: Actor, response: Response) -> DashboardRead:
    response.headers["Cache-Control"] = "no-store"
    return await study_plan.read_dashboard(db, actor.id)
