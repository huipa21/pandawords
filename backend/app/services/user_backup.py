"""``pandawords.user`` full backup (download) and restore (merge into the current user).

Export reuses the project-export pipeline: an owner-filtered snapshot, hashed media, the shared
serializer and an atomically published archive in a private directory. Restore reuses the
project-import validators and atomic merge, then — inside the same transaction — restores
preferences that are still at their defaults and records a restore receipt so that repeating
the same backup is a no-op.
"""

import asyncio
import hashlib
import shutil
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.core.record_ids import encode_rid
from app.db import user_backup as backup_repository
from app.db import user_restore as restore_repository
from app.domain.bundle import dump_data
from app.domain.bundle_import import ImportOptions, ImportPlan
from app.domain.bundle_manifest import DATA_FILE, ManifestHeader
from app.domain.bundle_serialize import BundleSource, serialize_bundle
from app.domain.identity import user_key
from app.domain.user_backup import (
    USER_FORMAT,
    AlreadyRestored,
    PreferenceMerge,
    RestoreSummary,
    merge_preferences,
)
from app.services.bundle_import import apply_bundle
from app.services.bundle_io import LoadedBundle, export_bundle
from app.services.bundle_source import fingerprint, same_source
from app.services.project_export import (
    ATTRIBUTION,
    ProjectArchive,
    _media_files,  # pyright: ignore[reportPrivateUsage]
    _without_skipped,  # pyright: ignore[reportPrivateUsage]
)
from app.services.project_import import bundle_warnings, private_dir, receive_bundle

logger = structlog.get_logger()
USER_FORMATS = frozenset({USER_FORMAT})


def _write(
    settings: Settings, subject: str, owner: RecordID, source: BundleSource, directory: Path
) -> ProjectArchive:
    media = _media_files(settings.media_dir, source.media)
    source = _without_skipped(source, media)
    data = serialize_bundle(owner, USER_FORMAT, source)
    account = source.user or {}
    shared = any(item.owner == "shared" for item in [*data.records, *data.edges, *data.media])
    now = datetime.now(UTC)
    header = ManifestHeader(
        format=USER_FORMAT,
        app_version=settings.app_version,
        created_at=now,
        source_lang=account.get("source_lang", settings.source_language),
        target_lang=account.get("target_lang", settings.target_language),
        attribution=ATTRIBUTION if shared else [],
        source=fingerprint(settings, subject, hashlib.sha256(dump_data(data)).hexdigest()),
    )
    path = directory / "backup.tar.gz"
    export_bundle(path, header, data, media.files)
    filename = f"pandawords-backup-{now:%Y%m%d}.pandawords-user.tar.gz"
    return ProjectArchive(path, filename, len(media.skipped))


async def export_user(db: AsyncSurrealConnection, settings: Settings, owner: str) -> ProjectArchive:
    """Build a validated ``pandawords.user`` archive; the caller must call ``cleanup``."""
    source = await backup_repository.load_user(db, owner)
    owner_record = RecordID("user", user_key(owner))
    work_dir = settings.bundle_work_dir
    if work_dir is not None:
        await asyncio.to_thread(work_dir.mkdir, parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="pandawords-backup-", dir=work_dir))
    try:
        archive = await asyncio.to_thread(_write, settings, owner, owner_record, source, directory)
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, directory, ignore_errors=True)
        logger.warning("user_backup_failed", stage="archive")
        raise
    if archive.skipped_media:
        logger.warning("user_backup_media_skipped", count=archive.skipped_media)
    return archive


def _summary(
    plan: ImportPlan, merge: PreferenceMerge, progress: bool, same: bool, warnings: list[str]
) -> RestoreSummary:
    notices = set(plan.notices) | ({"preference_kept"} if merge.kept else set())
    return RestoreSummary(
        project_ids=[encode_rid(project, "project") for project in plan.projects],
        progress_imported=progress,
        same_source=same,
        created=dict(sorted(plan.created.items())),
        merged=dict(sorted(plan.merged.items())),
        skipped=dict(sorted(plan.skipped.items())),
        conflicts=sorted(notices),
        warnings=warnings,
        already_restored=False,
        preferences_restored=sorted(merge.restored),
        preferences_kept=sorted(merge.kept),
    )


def _again(stored: dict[str, Any]) -> RestoreSummary:
    return RestoreSummary.model_validate({**stored, "already_restored": True})


def _data_sha256(bundle: LoadedBundle) -> str:
    return next(e.sha256 for e in bundle.archive.manifest.entries if e.path == DATA_FILE)


async def _restore(
    db: AsyncSurrealConnection,
    settings: Settings,
    owner: str,
    bundle: LoadedBundle,
    include_progress: bool,
) -> RestoreSummary:
    user = RecordID("user", user_key(owner))
    digest = _data_sha256(bundle)
    if (stored := await restore_repository.read_receipt(db, user, digest)) is not None:
        return _again(stored)
    same = same_source(settings, owner, bundle.archive.manifest)
    warnings = await bundle_warnings(settings, bundle)
    data = bundle.data
    fallback = data.projects[0].ref if data.projects else None
    result: list[RestoreSummary] = []

    async def finalize(txn: UUID, plan: ImportPlan) -> None:
        if (earlier := await restore_repository.read_receipt(db, user, digest, txn)) is not None:
            raise AlreadyRestored(earlier)
        merge = PreferenceMerge()
        if data.preferences is not None:
            merge = merge_preferences(
                await restore_repository.read_account(db, user, txn), data.preferences
            )
            await restore_repository.write_preferences(db, user, merge, txn)
        summary = _summary(plan, merge, include_progress, same, warnings)
        stored = summary.model_dump(mode="json", exclude={"already_restored"})
        await restore_repository.write_receipt(db, user, digest, plan.projects, stored, txn)
        result[:] = [summary]

    options = ImportOptions(include_progress, fallback_project=fallback)
    try:
        await apply_bundle(db, settings, owner, bundle, options, finalize)
    except AlreadyRestored as again:
        return _again(again.summary)
    return result[0]


async def restore_user(
    db: AsyncSurrealConnection,
    settings: Settings,
    owner: str,
    chunks: AsyncIterator[bytes],
    include_progress: bool,
) -> RestoreSummary:
    """Validate the whole backup, then merge it into ``owner`` in one transaction."""
    directory = await private_dir(settings)
    bundle: LoadedBundle | None = None
    try:
        bundle = await receive_bundle(settings, chunks, directory, USER_FORMATS)
        return await _restore(db, settings, owner, bundle, include_progress)
    finally:
        if bundle is not None:
            await asyncio.to_thread(bundle.close)
        await asyncio.to_thread(shutil.rmtree, directory, ignore_errors=True)
