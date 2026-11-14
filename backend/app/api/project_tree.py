from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.project_tree import (
    ProjectMembershipRead,
    ProjectTreePage,
    ProjectVisibilityUpdate,
    TreeTable,
)
from app.services import project_tree

router = APIRouter(prefix="/api/projects", tags=["project-tree"])
Actor = Annotated[User, Depends(current_user)]


@router.get("/{project_id}/tree")
async def read_tree(
    project_id: str,
    db: Db,
    actor: Actor,
    response: Response,
    page: Annotated[int, Query(ge=1, le=2_147_483_647)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    include_hidden: bool = False,
) -> ProjectTreePage:
    response.headers["Cache-Control"] = "no-store"
    return await project_tree.read_tree(db, actor.id, project_id, page, page_size, include_hidden)


@router.patch("/{project_id}/tree/{table}/{target_id}/visibility")
async def set_visibility(
    project_id: str,
    table: TreeTable,
    target_id: str,
    data: ProjectVisibilityUpdate,
    db: Db,
    actor: Actor,
    response: Response,
) -> ProjectMembershipRead:
    response.headers["Cache-Control"] = "no-store"
    return await project_tree.set_visibility(
        db, actor.id, project_id, table, target_id, data.hidden
    )
