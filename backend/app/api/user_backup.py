from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import FileResponse

from app.api.dependencies import Db, current_user, get_settings
from app.api.project_export import _ArchiveResponse  # pyright: ignore[reportPrivateUsage]
from app.core.config import Settings
from app.core.errors import BundleError
from app.domain.auth import User
from app.domain.user_backup import RestoreSummary
from app.services import user_backup

router = APIRouter(prefix="/api/me", tags=["backup"])


@router.get(
    "/backup",
    response_class=FileResponse,
    responses={200: {"content": {"application/gzip": {}}, "description": "User backup."}},
)
async def download_backup(
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    actor: Annotated[User, Depends(current_user)],
) -> FileResponse:
    """Download all of the current user's data as a ``pandawords.user`` bundle."""
    archive = await user_backup.export_user(db, settings, actor.id)
    try:
        return _ArchiveResponse(archive)
    except BaseException:
        archive.cleanup()
        raise


@router.post(
    "/restore",
    response_model=RestoreSummary,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/gzip": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def restore_backup(
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    actor: Annotated[User, Depends(current_user)],
    include_progress: Annotated[bool, Query()] = True,
) -> RestoreSummary:
    """Merge a ``pandawords.user`` backup into the current user (account fields untouched)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > settings.bundle_import_max_bytes:
        raise BundleError("too_large", "upload", status=413)
    return await user_backup.restore_user(
        db, settings, actor.id, request.stream(), include_progress
    )
