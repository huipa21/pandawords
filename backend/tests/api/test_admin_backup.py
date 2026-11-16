import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import Settings
from app.services.site_backup import SiteBackupRunner
from app.services.site_backup_store import BackupLock, sidecar
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
URL = "/api/admin/backups"


@pytest.fixture
def test_settings(session_db_settings: Settings, tmp_path: Path) -> Settings:
    return session_db_settings.model_copy(
        update={
            "media_dir": tmp_path / "media",
            "site_backup_dir": tmp_path / "backups",
            "lexicon_dir": tmp_path / "lexicon",
        }
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", URL),
        ("POST", URL),
        ("GET", f"{URL}/site-20260101T000000000000Z.tar.gz"),
        ("DELETE", f"{URL}/site-20260101T000000000000Z.tar.gz"),
    ],
)
async def test_only_admins_reach_site_backups(
    client: AsyncClient, make_user: UserFactory, method: str, path: str
) -> None:
    assert (await client.request(method, path)).status_code == 401
    user = await make_user()
    response = await client.request(
        method, path, headers=bearer(await login(client, user.username))
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


async def test_admin_creates_lists_and_downloads(
    app: FastAPI, client: AsyncClient, make_user: UserFactory, test_settings: Settings
) -> None:
    admin = await make_user(role="admin")
    headers = bearer(await login(client, admin.username))
    test_settings.media_dir.mkdir(parents=True)
    (test_settings.media_dir / "a.webp").write_bytes(b"image")

    started = await client.post(URL, headers=headers)
    assert started.status_code == 202, started.text
    assert started.headers["cache-control"] == "no-store"
    runner: SiteBackupRunner = app.state.site_backup_runner
    conflict = await client.post(URL, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "site_backup.in_progress"
    assert runner.task is not None
    await runner.task

    listing = (await client.get(URL, headers=headers)).json()
    assert listing["running"] is False and listing["last_error"] is None
    [backup] = listing["backups"]
    download = await client.get(f"{URL}/{backup['name']}", headers=headers)
    assert download.status_code == 200
    assert download.headers["cache-control"] == "no-store"
    assert "attachment" in download.headers["content-disposition"]
    assert hashlib.sha256(download.content).hexdigest() == backup["sha256"]

    for name in ("..%2F..%2Fetc%2Fpasswd", "site-20260101T000000000000Z.tar.gz", "manifest.json"):
        assert (await client.get(f"{URL}/{name}", headers=headers)).status_code == 404


async def test_no_site_restore_endpoint(client: AsyncClient) -> None:
    paths = (await client.get("/api/openapi.json")).json()["paths"]
    assert [path for path in paths if "restore" in path] == ["/api/me/restore"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[URL + "/{name}"]) == {"get", "delete"}


async def test_admin_deletes_only_completed_backups_under_lock(
    client: AsyncClient, make_user: UserFactory, test_settings: Settings
) -> None:
    admin = await make_user(role="admin")
    headers = bearer(await login(client, admin.username))
    directory = test_settings.site_backup_dir
    directory.mkdir()
    path = directory / "site-20260101T000000000000Z.tar.gz"
    path.write_bytes(b"archive")
    sidecar(path).write_text(f"{'a' * 64}  {path.name}\n", encoding="ascii")
    unrelated = directory / "keep.txt"
    unrelated.write_text("keep", encoding="ascii")

    lock = BackupLock(directory, test_settings.site_backup_lock_stale_seconds).acquire()
    try:
        conflict = await client.delete(f"{URL}/{path.name}", headers=headers)
        assert conflict.status_code == 409
        assert path.exists() and sidecar(path).exists()
    finally:
        lock.release()
    for name in ("keep.txt", "site-20260102T000000000000Z.tar.gz", "..%2Fkeep.txt"):
        assert (await client.delete(f"{URL}/{name}", headers=headers)).status_code == 404
    deleted = await client.delete(f"{URL}/{path.name}", headers=headers)
    assert deleted.status_code == 204
    assert deleted.headers["cache-control"] == "no-store"
    assert not path.exists() and not sidecar(path).exists()
    assert unrelated.read_text("ascii") == "keep"
    assert (await client.get(URL, headers=headers)).json()["backups"] == []
    assert (await client.delete(f"{URL}/{path.name}", headers=headers)).status_code == 404
