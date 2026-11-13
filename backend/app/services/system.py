from typing import Annotated, cast

from fastapi import Depends, Request
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.db.client import check_database, get_db


async def check_readiness(
    request: Request, db: Annotated[AsyncSurrealConnection, Depends(get_db)]
) -> None:
    settings = cast(Settings, request.app.state.settings)
    await check_database(db, settings.surreal_timeout_seconds)
