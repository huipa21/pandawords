from __future__ import annotations

import os
import tarfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.backup.schedule import run_schedule
from app.core.config import Settings
from app.db import site_backup as db_backup
from app.db.site_backup_test_support import table_rows
from app.db.test_support import isolated_database, write_probe
from app.db.test_support import test_database_settings as fresh_settings
from app.domain.auth import UserCreate
from app.domain.site_backup import SiteBackupError, SiteBackupManifest
from app.services import site_backup, site_backup_archive, site_backup_store
from app.services.auth import create_user
from app.services.site_restore import restore_site

pytestmark = pytest.mark.integration


def _dirs(settings: Settings, root: Path, **extra: object) -> Settings:
    return settings.model_copy(
        update={
            "media_dir": root / "media",
            "site_backup_dir": root / "backups",
            "lexicon_dir": root / "lexicon",
            **extra,
        }
    )


@pytest.fixture
async def source(
    job_db: AsyncWsSurrealConnection, job_settings: Settings, tmp_path: Path
) -> Settings:
    settings = _dirs(job_settings, tmp_path / "source")
    await create_user(job_db, UserCreate(username="backup_user", password="secret-password-1"))
    media = settings.media_dir
    (media / "images" / "ab").mkdir(parents=True)
    (media / "images" / "ab" / "cat.webp").write_bytes(b"cat-image" * 100)
    (media / "audio.mp3").write_bytes(b"\x00\x01audio")
    (media / ".env").write_text("JWT_SECRET=do-not-copy")
    (media / "server.key").write_text("private key")
    settings.lexicon_dir.mkdir(parents=True)
    (settings.lexicon_dir / "lexicon.sqlite").write_bytes(b"lexicon bytes")
    return settings


@pytest.fixture
async def target(tmp_path: Path) -> AsyncIterator[tuple[Settings, AsyncWsSurrealConnection]]:
    settings = _dirs(fresh_settings(), tmp_path / "target")
    async with isolated_database(settings, migrate=False) as connection:
        yield settings, connection


def _members(path: Path) -> list[str]:
    with tarfile.open(path, "r:gz") as archive:
        return archive.getnames()


async def test_backup_restore_round_trip(
    source: Settings,
    job_db: AsyncWsSurrealConnection,
    target: tuple[Settings, AsyncWsSurrealConnection],
) -> None:
    created = await site_backup.create_backup(source, "manual")
    path = source.site_backup_dir / created.name
    assert site_backup_store.list_backups(source.site_backup_dir) == [created]
    assert site_backup_archive.sha256_file(path)[0] == created.sha256
    names = _members(path)
    assert names[:2] == ["manifest.json", "db.surql"]
    assert sorted(names[2:]) == ["media/audio.mp3", "media/images/ab/cat.webp"]
    assert not any("lexicon" in name or "env" in name or name.endswith(".key") for name in names)
    with tarfile.open(path, "r:gz") as archive:
        stream = archive.extractfile("manifest.json")
        assert stream is not None
        manifest = SiteBackupManifest.model_validate_json(stream.read())
    assert manifest.format == "pandawords.site" and manifest.trigger == "manual"
    assert manifest.database.tables["user"] >= 1
    if os.name == "posix":
        assert source.site_backup_dir.stat().st_mode & 0o777 == 0o700
        assert path.stat().st_mode & 0o777 == 0o600

    settings, restored = target
    result = await restore_site(settings, path, replace=False)
    assert result.media_files == 2 and result.pre_restore_export is None
    assert await db_backup.table_counts(restored) == manifest.database.tables
    for table in ("user", "_migration"):
        assert await table_rows(restored, table) == await table_rows(job_db, table)
    restored_media = settings.media_dir
    assert (restored_media / "images" / "ab" / "cat.webp").read_bytes() == b"cat-image" * 100
    assert (restored_media / "audio.mp3").read_bytes() == b"\x00\x01audio"
    assert sorted(path.name for path in restored_media.iterdir()) == ["audio.mp3", "images"]


async def test_restore_never_touches_nonempty_target_without_replace(
    source: Settings, target: tuple[Settings, AsyncWsSurrealConnection]
) -> None:
    created = await site_backup.create_backup(source, "manual")
    settings, connection = target
    await write_probe(connection, "keep")
    settings.media_dir.mkdir(parents=True)
    (settings.media_dir / "existing.txt").write_text("keep")
    archive = source.site_backup_dir / created.name
    with pytest.raises(SiteBackupError) as failure:
        await restore_site(settings, archive, replace=False)
    assert failure.value.stage == "target"
    assert await table_rows(connection, "migration_probe") != []
    assert [path.name for path in settings.media_dir.iterdir()] == ["existing.txt"]

    result = await restore_site(settings, archive, replace=True)
    assert result.pre_restore_export is not None
    assert (settings.site_backup_dir / result.pre_restore_export).is_file()
    assert "migration_probe" not in await db_backup.table_counts(connection)
    assert not (settings.media_dir / "existing.txt").exists()


async def test_database_failure_leaves_media_untouched(
    source: Settings,
    target: tuple[Settings, AsyncWsSurrealConnection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await site_backup.create_backup(source, "manual")
    settings, _ = target
    settings.media_dir.mkdir(parents=True)
    (settings.media_dir / "existing.txt").write_text("keep")

    async def broken(*_args: object) -> None:
        raise RuntimeError("import failed")

    monkeypatch.setattr(db_backup, "import_database", broken)
    with pytest.raises(SiteBackupError) as failure:
        await restore_site(settings, source.site_backup_dir / created.name, replace=False)
    assert failure.value.stage == "database"
    assert sorted(path.name for path in settings.media_dir.iterdir()) == ["existing.txt"]
    assert not (settings.site_backup_dir / site_backup_store.LOCK).exists()


async def test_scheduled_backups_apply_retention(source: Settings) -> None:
    settings = source.model_copy(update={"site_backup_retain": 2})
    now = [datetime(2026, 1, 1, 3, 0, tzinfo=UTC)]

    async def sleep(seconds: float) -> None:
        now[0] += timedelta(seconds=seconds)

    await run_schedule(settings, clock=lambda: now[0], sleep=sleep, iterations=3)
    backups = site_backup_store.list_backups(settings.site_backup_dir)
    assert len(backups) == 2
    assert now[0] >= datetime(2026, 1, 3, 3, 30, tzinfo=UTC)
    files = sorted(path.name for path in settings.site_backup_dir.iterdir())
    assert files == sorted(
        [item.name for item in backups] + [f"{item.name}.sha256" for item in backups]
    )
    for item in backups:
        with tarfile.open(settings.site_backup_dir / item.name, "r:gz") as archive:
            stream = archive.extractfile("manifest.json")
            assert stream is not None
            assert SiteBackupManifest.model_validate_json(stream.read()).trigger == "scheduled"


@pytest.mark.parametrize("stage", ["database", "verify"])
async def test_failed_backup_keeps_previous_and_publishes_nothing(
    source: Settings, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    settings = source.model_copy(update={"site_backup_retain": 1})
    previous = await site_backup.create_backup(settings, "manual")

    def broken(*_args: object, **_kwargs: object) -> None:
        raise site_backup_archive.ArchiveError("integrity", "corrupt")

    async def broken_export(*_args: object) -> None:
        raise RuntimeError("export failed")

    if stage == "database":
        monkeypatch.setattr(db_backup, "export_database", broken_export)
    else:
        monkeypatch.setattr(site_backup_archive, "read_archive", broken)
    with pytest.raises(SiteBackupError) as failure:
        await site_backup.create_backup(settings, "scheduled")
    assert failure.value.stage == stage
    assert site_backup_store.list_backups(settings.site_backup_dir) == [previous]
    assert sorted(path.name for path in settings.site_backup_dir.iterdir()) == [
        previous.name,
        f"{previous.name}.sha256",
    ]


async def test_concurrent_backups_are_rejected(source: Settings) -> None:
    lock = site_backup.acquire_lock(source)
    try:
        with pytest.raises(SiteBackupError) as failure:
            await site_backup.create_backup(source, "manual")
        assert failure.value.status == 409
    finally:
        lock.release()
    stale = site_backup.acquire_lock(source)
    stale.held = False
    old = datetime.now(UTC).timestamp() - source.site_backup_lock_stale_seconds - 10
    os.utime(stale.path, (old, old))
    assert (await site_backup.create_backup(source, "manual")).size > 0
    assert not stale.path.exists()
