from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.relations import RelationCreate, RelationRead, RelationResult
from app.services import relations

router = APIRouter(prefix="/api/relations", tags=["relations"])
Actor = Annotated[User, Depends(current_user)]


@router.post("")
async def create_relation(
    data: RelationCreate, db: Db, actor: Actor, response: Response
) -> RelationResult:
    result = await relations.create(db, actor.id, data)
    response.status_code = 201 if result.created else 200
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("")
async def list_relations(
    db: Db,
    actor: Actor,
    response: Response,
    sense_id: Annotated[str, Query(min_length=1, max_length=16384)],
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RelationRead]:
    response.headers["Cache-Control"] = "no-store"
    return await relations.list_relations(db, actor.id, sense_id, page, page_size)


@router.delete("/{id}", status_code=204)
async def delete_relation(id: str, db: Db, actor: Actor) -> None:
    await relations.delete(db, actor.id, id)
