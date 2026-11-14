import asyncio
from typing import Annotated, cast

from fastapi import Depends, Request
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError
from app.db.client import check_database, get_db


async def check_readiness(
    request: Request, db: Annotated[AsyncSurrealConnection, Depends(get_db)]
) -> None:
    settings = cast(Settings, request.app.state.settings)
    await check_database(db, settings.surreal_timeout_seconds)
    initialization = cast(asyncio.Task[None], request.app.state.auth_initialization)
    if (
        not initialization.done()
        or initialization.cancelled()
        or initialization.exception() is not None
    ):
        raise AppError("auth.unavailable", 503, "Authentication is unavailable.")
