from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import Db, current_user, get_settings
from app.core.config import Settings
from app.domain.auth import User
from app.services import media

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get(
    "/{rid}",
    response_class=Response,
    responses={200: {"description": "Authorized internal nginx media delivery."}},
)
async def get_media(
    rid: str,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(current_user)],
) -> Response:
    internal_uri, mime = await media.delivery(db, settings, rid, user.id)
    return Response(
        headers={
            "X-Accel-Redirect": internal_uri,
            "Content-Type": mime,
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        }
    )
