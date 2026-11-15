from typing import Annotated, override

from fastapi import APIRouter, Depends
from starlette.responses import FileResponse
from starlette.types import Receive, Scope, Send

from app.api.dependencies import Db, current_user, get_settings
from app.core.config import Settings
from app.domain.auth import User
from app.services import project_export
from app.services.project_export import ProjectArchive

router = APIRouter(prefix="/api/projects", tags=["projects"])


class _ArchiveResponse(FileResponse):
    """Stream the archive from disk, then remove its private directory even on disconnect."""

    def __init__(self, archive: ProjectArchive) -> None:
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if archive.skipped_media:
            headers["X-PandaWords-Skipped-Media"] = str(archive.skipped_media)
        super().__init__(
            archive.path, media_type="application/gzip", filename=archive.filename, headers=headers
        )
        self.archive = archive

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.archive.cleanup()


@router.get(
    "/{id}/export",
    response_class=FileResponse,
    responses={200: {"content": {"application/gzip": {}}, "description": "Project bundle."}},
)
async def export_project(
    id: str,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    actor: Annotated[User, Depends(current_user)],
) -> FileResponse:
    archive = await project_export.export_project(db, settings, actor.id, id)
    try:
        return _ArchiveResponse(archive)
    except BaseException:
        archive.cleanup()
        raise
