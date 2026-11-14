from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.jobs import JobRead
from app.services import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{id}")
async def get_job(
    id: str, response: Response, db: Db, user: Annotated[User, Depends(current_user)]
) -> JobRead:
    response.headers["Cache-Control"] = "no-store"
    return await jobs.read(db, id, user.id)
