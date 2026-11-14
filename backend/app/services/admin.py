from anyio import to_thread
from surrealdb import AsyncSurrealConnection

from app.core.errors import AppError
from app.core.security import generate_refresh_token, hash_password
from app.db import admin as repository
from app.domain.admin import AdminUserCreate, AdminUserPage, AdminUserResult, AdminUserUpdate
from app.domain.auth import UserCreate
from app.domain.identity import user_key


async def list_users(db: AsyncSurrealConnection, page: int, page_size: int) -> AdminUserPage:
    return await repository.list_users(db, page, page_size)


async def create_user(
    db: AsyncSurrealConnection, actor: str, data: AdminUserCreate
) -> AdminUserResult:
    temporary = generate_refresh_token()
    password_hash = await to_thread.run_sync(hash_password, temporary)
    user = await repository.create_user(
        db,
        actor,
        UserCreate(username=data.username, password=temporary, role=data.role),
        password_hash,
    )
    return AdminUserResult(user=user, temporary_password=temporary)


async def update_user(
    db: AsyncSurrealConnection, actor: str, subject: str, data: AdminUserUpdate
) -> AdminUserResult:
    try:
        user_key(subject)
    except ValueError:
        raise AppError("admin.user_not_found", 404, "User not found.") from None
    temporary = generate_refresh_token() if data.reset_password else None
    password_hash = (
        await to_thread.run_sync(hash_password, temporary) if temporary is not None else None
    )
    user = await repository.update_user(db, actor, subject, data, password_hash)
    return AdminUserResult(user=user, temporary_password=temporary)
