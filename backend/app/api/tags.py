from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.tags import (
    TagAssignment,
    TagAssignmentRead,
    TagCreate,
    TagListQuery,
    TagRead,
    TagUpdate,
)
from app.services import tags

router = APIRouter(prefix="/api/tags", tags=["tags"])
Actor = Annotated[User, Depends(current_user)]


@router.post("", status_code=201)
async def create_tag(data: TagCreate, db: Db, actor: Actor, response: Response) -> TagRead:
    response.headers["Cache-Control"] = "no-store"
    return await tags.create(db, actor.id, data)


@router.get("")
async def list_tags(
    query: Annotated[TagListQuery, Query()], db: Db, actor: Actor, response: Response
) -> list[TagRead]:
    response.headers["Cache-Control"] = "no-store"
    return await tags.list_tags(db, actor.id)


@router.get("/assignments")
async def list_assignments(
    query: Annotated[TagAssignment, Query()],
    db: Db,
    actor: Actor,
    response: Response,
) -> list[TagAssignmentRead]:
    response.headers["Cache-Control"] = "no-store"
    return await tags.memberships(db, actor.id, query.target_table, query.target_id)


@router.get("/{id}")
async def read_tag(id: str, db: Db, actor: Actor, response: Response) -> TagRead:
    response.headers["Cache-Control"] = "no-store"
    return await tags.read(db, actor.id, id)


@router.patch("/{id}")
async def update_tag(
    id: str,
    data: TagUpdate,
    db: Db,
    actor: Actor,
    response: Response,
) -> TagRead:
    response.headers["Cache-Control"] = "no-store"
    return await tags.update(db, actor.id, id, data)


@router.delete("/{id}", status_code=204)
async def delete_tag(id: str, db: Db, actor: Actor) -> Response:
    await tags.delete(db, actor.id, id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.put("/{id}/members", status_code=204)
async def assign_tag(id: str, data: TagAssignment, db: Db, actor: Actor) -> Response:
    await tags.assign(db, actor.id, id, data.target_table, data.target_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.delete("/{id}/members", status_code=204)
async def remove_tag(
    id: str,
    query: Annotated[TagAssignment, Query()],
    db: Db,
    actor: Actor,
) -> Response:
    await tags.assign(db, actor.id, id, query.target_table, query.target_id, remove=True)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
