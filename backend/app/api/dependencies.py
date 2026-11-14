from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import invalid_credentials
from app.db.client import get_db
from app.domain.auth import User
from app.services import auth

bearer = HTTPBearer(auto_error=False)
Db = Annotated[AsyncSurrealConnection, Depends(get_db)]


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


async def current_user(
    request: Request,
    db: Annotated[AsyncSurrealConnection, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credential is None:
        raise invalid_credentials()
    user = await auth.current_user(db, settings, credential.credentials)
    if user.must_change_password and request.url.path not in {
        "/api/auth/me",
        "/api/auth/password",
        "/api/auth/logout",
    }:
        raise auth.password_change_required()
    return user


async def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise AppError("auth.forbidden", 403, "Access denied.")
    return user
