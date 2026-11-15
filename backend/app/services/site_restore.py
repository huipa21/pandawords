"""Operator site restore core used by `deploy/restore.sh` (via `python -m app.backup restore`).

Stages: preflight (no mutation) → lock → extract to staging → target database check
(empty, or `replace` after a safety export) → import → verify counts → media swap → verify.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import structlog

from app.core.config import Settings
from app.db import site_backup as db_backup
from app.domain.site_backup import SiteBackupError, SiteBackupManifest, SiteRestoreResult
from app.services import site_backup_archive as archive
from app.services import site_backup_store as store
from app.services.site_backup import acquire_lock


def _verify(settings: Settings, path: Path) -> SiteBackupManifest:
    if not path.is_file():
        raise SiteBackupError("preflight", "Archive file not found.")
    marker = store.sidecar(path)
    try:
        if marker.is_file():
            expected = marker.read_text("ascii", errors="replace").split(" ", 1)[0].strip()
            if archive.sha256_file(path)[0] != expected:
                raise archive.ArchiveError("integrity", "Archive checksum does not match .sha256")
        return archive.read_archive(
            path,
            max_entries=settings.site_backup_max_entries,
            max_bytes=settings.site_backup_max_bytes,
        )
    except archive.ArchiveError as error:
        raise SiteBackupError(
            "preflight", f"Invalid site archive ({error.stage}): {error}"
        ) from None
    except OSError as error:
        message = f"Archive is unreadable: {type(error).__name__}"
        raise SiteBackupError("preflight", message) from None


async def preflight(settings: Settings, path: Path) -> SiteBackupManifest:
    """Fully verify an archive (format, version, paths, sizes, checksums) without writing."""
    return await asyncio.to_thread(_verify, settings, path)


def swap_media(root: Path, staging: Path) -> None:
    """Replace the media tree using same-volume renames, rolling back on failure."""
    old = root / f"{archive.INTERNAL_MEDIA_PREFIXES[1]}{uuid4().hex}"
    old.mkdir(mode=0o700)
    moved_old: list[str] = []
    moved_new: list[str] = []
    try:
        for entry in sorted(root.iterdir()):
            if not entry.name.startswith(archive.INTERNAL_MEDIA_PREFIXES):
                os.replace(entry, old / entry.name)
                moved_old.append(entry.name)
        for entry in sorted(staging.iterdir()):
            os.replace(entry, root / entry.name)
            moved_new.append(entry.name)
    except OSError:
        for name in reversed(moved_new):
            os.replace(root / name, staging / name)
        for name in reversed(moved_old):
            os.replace(old / name, root / name)
        old.rmdir()
        raise
    shutil.rmtree(old)


def _router(work: Path, staging: Path) -> Callable[[str], Path]:
    def destination(name: str) -> Path:
        if name == archive.DATABASE:
            return work / archive.DATABASE
        return archive.contained(staging, name.removeprefix(archive.MEDIA_PREFIX))

    return destination


async def _restore_database(
    settings: Settings, manifest: SiteBackupManifest, dump: Path, *, replace: bool
) -> tuple[str | None, int]:
    stage = "target"
    safety: str | None = None
    try:
        async with db_backup.connect(settings) as db:
            if not await db_backup.is_empty(db):
                if not replace:
                    raise SiteBackupError(
                        "target",
                        "Target database is not empty; nothing was changed. "
                        "Rerun with --replace to export it and restore over it.",
                    )
                stamp = f"{datetime.now(UTC):%Y%m%dT%H%M%S%f}Z"
                target = settings.site_backup_dir / f"pre-restore-{stamp}.surql"
                await db_backup.export_database(db, target)
                store.restrict(target)
                safety = target.name
                await db_backup.recreate_empty(db, settings.surreal_database)
            else:
                await db_backup.ensure_database(db, settings.surreal_database)
            stage = "database"
            await db_backup.import_database(db, dump)
            stage = "verify_database"
            counts = await db_backup.table_counts(db)
    except SiteBackupError:
        raise
    except Exception as error:
        structlog.get_logger().error(
            "site_restore_failed", stage=stage, error_type=type(error).__name__
        )
        hint = f" A safety export was saved as {safety}." if safety else ""
        raise SiteBackupError(
            stage, f"Database restore failed during {stage}: {type(error).__name__}.{hint}"
        ) from error
    if counts != manifest.database.tables:
        raise SiteBackupError(
            "verify_database", "Restored record counts do not match the archive manifest."
        )
    return safety, sum(counts.values())


async def _restore_media(settings: Settings, manifest: SiteBackupManifest, staging: Path) -> None:
    root = settings.media_dir
    try:
        await asyncio.to_thread(swap_media, root, staging)
    except OSError as error:
        raise SiteBackupError(
            "media", f"Media restore failed and was rolled back: {type(error).__name__}."
        ) from error
    excluded = [settings.site_backup_dir, settings.lexicon_dir]
    restored = await asyncio.to_thread(archive.collect_media, root, excluded)
    if [entry for _, entry in restored] != manifest.media:
        raise SiteBackupError("verify_media", "Restored media does not match the archive manifest.")


async def restore_site(settings: Settings, path: Path, *, replace: bool) -> SiteRestoreResult:
    manifest = await preflight(settings, path)
    lock = acquire_lock(settings)
    work = lock.path.parent / f"{store.WORK_PREFIX}{uuid4().hex}"
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    staging = settings.media_dir / f"{archive.INTERNAL_MEDIA_PREFIXES[0]}{uuid4().hex}"
    try:
        work.mkdir(mode=0o700)
        staging.mkdir(mode=0o700)
        try:
            await asyncio.to_thread(
                archive.read_archive,
                path,
                max_entries=settings.site_backup_max_entries,
                max_bytes=settings.site_backup_max_bytes,
                destination=_router(work, staging),
            )
        except archive.ArchiveError as error:
            raise SiteBackupError("extract", f"Archive staging failed: {error}") from None
        safety, records = await _restore_database(
            settings, manifest, work / archive.DATABASE, replace=replace
        )
        await _restore_media(settings, manifest, staging)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
        lock.release()
    structlog.get_logger().info(
        "site_restore_completed", records=records, media_files=len(manifest.media)
    )
    return SiteRestoreResult(
        archive_created_at=manifest.created_at,
        tables=len(manifest.database.tables),
        records=records,
        media_files=len(manifest.media),
        pre_restore_export=safety,
    )
