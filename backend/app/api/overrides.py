from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.dictionary import DictionaryTable
from app.domain.overrides import OverrideRead, OverrideUpdate
from app.services import overrides

router = APIRouter(prefix="/api/dictionary", tags=["overrides"])
Actor = Annotated[User, Depends(current_user)]


@router.get("/{table}/{id}/override", response_model_exclude_unset=True)
async def read_override(
    table: DictionaryTable, id: str, db: Db, actor: Actor, response: Response
) -> OverrideRead:
    response.headers["Cache-Control"] = "no-store"
    return await overrides.read(db, actor.id, table, id)


@router.put("/{table}/{id}/override", response_model_exclude_unset=True)
async def replace_override(
    table: DictionaryTable, id: str, data: OverrideUpdate, db: Db, actor: Actor, response: Response
) -> OverrideRead:
    response.headers["Cache-Control"] = "no-store"
    return await overrides.write(db, actor.id, table, id, data, action="put")


@router.patch("/{table}/{id}/override", response_model_exclude_unset=True)
async def update_override(
    table: DictionaryTable, id: str, data: OverrideUpdate, db: Db, actor: Actor, response: Response
) -> OverrideRead:
    response.headers["Cache-Control"] = "no-store"
    return await overrides.write(db, actor.id, table, id, data, action="patch")


@router.delete("/{table}/{id}/override", status_code=204)
async def reset_override(table: DictionaryTable, id: str, db: Db, actor: Actor) -> Response:
    await overrides.reset(db, actor.id, table, id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
