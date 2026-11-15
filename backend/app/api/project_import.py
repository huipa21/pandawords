from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import Db, current_user, get_settings
from app.core.config import Settings
from app.core.errors import BundleError
from app.domain.auth import User
from app.domain.bundle_import import ImportSummary
from app.services import project_import

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post(
    "/import",
    status_code=201,
    response_model=ImportSummary,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/gzip": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def import_project(
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    actor: Annotated[User, Depends(current_user)],
    include_progress: Annotated[bool | None, Query()] = None,
) -> ImportSummary:
    """Import a ``pandawords.project`` bundle as a new project of the current user.

    ``include_progress`` defaults to on only when the bundle was exported by this same user.
    """
    # Raw body (not multipart) so the upload is streamed to disk under a hard size bound.
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > settings.bundle_import_max_bytes:
        raise BundleError("too_large", "upload", status=413)
    return await project_import.import_project(
        db, settings, actor.id, request.stream(), include_progress
    )
