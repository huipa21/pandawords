from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import Db, require_admin
from app.domain.admin import AdminUserCreate, AdminUserPage, AdminUserResult, AdminUserUpdate
from app.domain.auth import User
from app.services import admin

router = APIRouter(prefix="/api/admin/users", tags=["admin"])
Admin = Annotated[User, Depends(require_admin)]


@router.get("")
async def list_users(
    db: Db,
    actor: Admin,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUserPage:
    response.headers["Cache-Control"] = "no-store"
    return await admin.list_users(db, page, page_size)


@router.post("", status_code=201)
async def create_user(
    data: AdminUserCreate, db: Db, actor: Admin, response: Response
) -> AdminUserResult:
    response.headers["Cache-Control"] = "no-store"
    return await admin.create_user(db, actor.id, data)


@router.patch("/{id}")
async def update_user(
    id: str, data: AdminUserUpdate, db: Db, actor: Admin, response: Response
) -> AdminUserResult:
    response.headers["Cache-Control"] = "no-store"
    return await admin.update_user(db, actor.id, id, data)
