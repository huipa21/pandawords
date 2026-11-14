from typing import Annotated

from fastapi import APIRouter, Depends, Response
from starlette.responses import FileResponse

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
    internal_uri, mime, path = await media.delivery(db, settings, rid, user.id)
    headers = {
        "X-Accel-Redirect": internal_uri,
        "Content-Type": mime,
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if settings.app_env == "development":
        return FileResponse(path, media_type=mime, headers=headers)
    return Response(headers=headers)
