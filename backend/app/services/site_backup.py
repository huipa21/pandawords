"""Create `pandawords.site` backups on demand (admin API) or on schedule (`app.backup`)."""

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import structlog

from app.core.config import Settings
from app.db import site_backup as db_backup
from app.domain.site_backup import (
    SITE_ATTRIBUTION,
    SITE_FORMAT,
    SITE_VERSION,
    SiteBackupDatabase,
    SiteBackupError,
    SiteBackupManifest,
    SiteBackupRead,
    SiteBackupStatus,
    SiteBackupTrigger,
    backup_in_progress,
)
from app.services import site_backup_archive as archive
from app.services import site_backup_store as store
from app.services.lexicon import LexiconReader


def check_locations(settings: Settings) -> Path:
    """The backup location must never be served as media nor hold media/lexicon content."""
    backups = settings.site_backup_dir.resolve()
    for other in (settings.media_dir.resolve(), settings.lexicon_dir.resolve()):
        if backups.is_relative_to(other) or other.is_relative_to(backups):
            raise SiteBackupError("configuration", "Backup directory overlaps media or lexicon.")
    return backups


def acquire_lock(settings: Settings) -> store.BackupLock:
    directory = check_locations(settings)
    return store.BackupLock(directory, settings.site_backup_lock_stale_seconds).acquire()


async def lexicon_version(settings: Settings) -> str | None:
    path = settings.lexicon_path or settings.lexicon_dir / "lexicon.sqlite"
    try:
        sources = await LexiconReader(path).sources()
    except Exception:
        return None
    parts = [f"{source.name}@{source.metadata.get('version', 'unknown')}" for source in sources]
    return ",".join(sorted(parts)) or None


async def _manifest(
    settings: Settings,
    trigger: SiteBackupTrigger,
    now: datetime,
    database: Path,
    media: list[tuple[Path, archive.SiteBackupFile]],
    tables: dict[str, int],
    version: str | None,
) -> SiteBackupManifest:
    digest, size = await asyncio.to_thread(archive.sha256_file, database)
    return SiteBackupManifest(
        format=SITE_FORMAT,
        version=SITE_VERSION,
        app_version=settings.app_version,
        created_at=now,
        trigger=trigger,
        lexicon_version=await lexicon_version(settings),
        source_lang=settings.source_language,
        target_lang=settings.target_language,
        attribution=SITE_ATTRIBUTION,
        database=SiteBackupDatabase(
            size=size, sha256=digest, surrealdb_version=version, tables=tables
        ),
        media=[entry for _, entry in media],
    )


async def _build(
    settings: Settings, trigger: SiteBackupTrigger, directory: Path, work: Path
) -> SiteBackupRead:
    stage = "database"
    try:
        now = datetime.now(UTC)
        database = work / archive.DATABASE
        async with db_backup.connect(settings) as db:
            await db_backup.export_database(db, database)
            tables = await db_backup.table_counts(db)
            version = await db_backup.server_version(db)
        stage = "media"
        excluded = [directory, settings.lexicon_dir]
        media = await asyncio.to_thread(archive.collect_media, settings.media_dir, excluded)
        manifest = await _manifest(settings, trigger, now, database, media, tables, version)
        stage = "archive"
        final = directory / store.new_name(now)
        partial = final.with_name(final.name + ".partial")
        try:
            await asyncio.to_thread(archive.write_archive, partial, manifest, database, media)
            stage = "verify"
            await asyncio.to_thread(
                archive.read_archive,
                partial,
                max_entries=settings.site_backup_max_entries,
                max_bytes=settings.site_backup_max_bytes,
            )
            digest, _ = await asyncio.to_thread(archive.sha256_file, partial)
            stage = "publish"
            await asyncio.to_thread(store.publish, partial, final, digest)
        finally:
            partial.unlink(missing_ok=True)
    except SiteBackupError:
        raise
    except Exception as error:
        structlog.get_logger().error(
            "site_backup_failed", stage=stage, trigger=trigger, error_type=type(error).__name__
        )
        raise SiteBackupError(stage, f"Site backup failed during {stage}.") from error
    result = store.list_backups(directory)
    return next(item for item in result if item.name == final.name)


async def create_backup(
    settings: Settings, trigger: SiteBackupTrigger, lock: store.BackupLock | None = None
) -> SiteBackupRead:
    """Publish one verified archive, then prune; a failure never removes older backups."""
    held = lock or acquire_lock(settings)
    directory = held.path.parent
    work = directory / f"{store.WORK_PREFIX}{uuid4().hex}"
    try:
        await asyncio.to_thread(store.clean_incomplete, directory)
        work.mkdir(mode=0o700)
        created = await _build(settings, trigger, directory, work)
        try:
            removed = await asyncio.to_thread(
                store.apply_retention, directory, settings.site_backup_retain
            )
        except OSError as error:
            structlog.get_logger().warning(
                "site_backup_retention_failed", error=type(error).__name__
            )
            removed = []
        structlog.get_logger().info(
            "site_backup_created", trigger=trigger, size=created.size, pruned=len(removed)
        )
        return created
    finally:
        shutil.rmtree(work, ignore_errors=True)
        held.release()


class SiteBackupRunner:
    """One in-process on-demand backup at a time; the file lock covers other processes."""

    def __init__(self) -> None:
        self.task: asyncio.Task[SiteBackupRead | None] | None = None
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def start(self, settings: Settings) -> None:
        if self.running:
            raise backup_in_progress()
        lock = acquire_lock(settings)
        self.last_error = None
        self.task = asyncio.create_task(self._run(settings, lock), name="site_backup")

    async def _run(self, settings: Settings, lock: store.BackupLock) -> SiteBackupRead | None:
        try:
            return await create_backup(settings, "manual", lock)
        except SiteBackupError as error:
            self.last_error = error.stage
        except Exception as error:
            self.last_error = "internal"
            structlog.get_logger().error("site_backup_crashed", error_type=type(error).__name__)
        return None

    def status(self, settings: Settings) -> SiteBackupStatus:
        return SiteBackupStatus(
            running=self.running,
            last_error=self.last_error,
            backups=store.list_backups(check_locations(settings)),
        )


def download_path(settings: Settings, name: str) -> Path:
    return store.resolve(check_locations(settings), name)


async def delete_backup(settings: Settings, name: str) -> None:
    lock = acquire_lock(settings)
    try:
        path = store.resolve(lock.path.parent, name)
        await asyncio.to_thread(path.unlink)
        await asyncio.to_thread(store.sidecar(path).unlink, missing_ok=True)
        structlog.get_logger().info("site_backup_deleted", name=name)
    except OSError as error:
        structlog.get_logger().error("site_backup_delete_failed", error_type=type(error).__name__)
        raise SiteBackupError("delete", "Could not delete the site backup.") from error
    finally:
        lock.release()
