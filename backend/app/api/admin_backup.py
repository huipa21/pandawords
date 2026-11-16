"""Admin-only on-demand site backups. There is deliberately no restore/upload endpoint."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse

from app.api.dependencies import get_settings, require_admin
from app.core.config import Settings
from app.domain.auth import User
from app.domain.site_backup import SiteBackupStatus
from app.services import site_backup

router = APIRouter(prefix="/api/admin/backups", tags=["admin"])
Admin = Annotated[User, Depends(require_admin)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _runner(request: Request) -> site_backup.SiteBackupRunner:
    state = request.app.state
    if not hasattr(state, "site_backup_runner"):
        state.site_backup_runner = site_backup.SiteBackupRunner()
    return cast(site_backup.SiteBackupRunner, state.site_backup_runner)


Runner = Annotated[site_backup.SiteBackupRunner, Depends(_runner)]


@router.get("")
async def list_backups(
    actor: Admin, settings: AppSettings, runner: Runner, response: Response
) -> SiteBackupStatus:
    response.headers["Cache-Control"] = "no-store"
    return runner.status(settings)


@router.post("", status_code=202)
async def create_backup(
    actor: Admin, settings: AppSettings, runner: Runner, response: Response
) -> SiteBackupStatus:
    response.headers["Cache-Control"] = "no-store"
    runner.start(settings)
    return runner.status(settings)


@router.get(
    "/{name}",
    response_class=FileResponse,
    responses={200: {"content": {"application/gzip": {}}}},
)
async def download_backup(actor: Admin, settings: AppSettings, name: str) -> FileResponse:
    path = site_backup.download_path(settings, name)
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=path.name,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{name}", status_code=204)
async def delete_backup(actor: Admin, settings: AppSettings, name: str) -> Response:
    await site_backup.delete_backup(settings, name)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
