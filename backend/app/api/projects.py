from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.projects import ProjectCreate, ProjectPage, ProjectRead, ProjectUpdate
from app.services import projects

router = APIRouter(prefix="/api/projects", tags=["projects"])
Actor = Annotated[User, Depends(current_user)]


@router.post("", status_code=201)
async def create_project(
    data: ProjectCreate, db: Db, actor: Actor, response: Response
) -> ProjectRead:
    response.headers["Cache-Control"] = "no-store"
    return await projects.create_project(db, actor.id, data)


@router.get("")
async def list_projects(
    db: Db,
    actor: Actor,
    response: Response,
    page: Annotated[int, Query(ge=1, le=2_147_483_647)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProjectPage:
    response.headers["Cache-Control"] = "no-store"
    return await projects.list_projects(db, actor.id, page, page_size)


@router.get("/{id}")
async def read_project(id: str, db: Db, actor: Actor, response: Response) -> ProjectRead:
    response.headers["Cache-Control"] = "no-store"
    return await projects.read_project(db, actor.id, id)


@router.patch("/{id}")
async def update_project(
    id: str, data: ProjectUpdate, db: Db, actor: Actor, response: Response
) -> ProjectRead:
    response.headers["Cache-Control"] = "no-store"
    return await projects.update_project(db, actor.id, id, data)


@router.delete("/{id}", status_code=204)
async def delete_project(id: str, db: Db, actor: Actor) -> Response:
    await projects.delete_project(db, actor.id, id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
