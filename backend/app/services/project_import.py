"""``pandawords.project`` import: bounded upload -> full validation -> atomic merge.

Every import creates a new project for the importer (repeating an import yields another
copy); shared dictionary rows merge by ID, existing memory/overrides are kept and completed
attempts are never duplicated. The upload and staging live in a private directory under
``BUNDLE_WORK_DIR`` that is removed whatever happens.
"""

import asyncio
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import IO

from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.errors import BundleError
from app.core.record_ids import encode_rid
from app.domain.bundle_import import ImportOptions, ImportSummary
from app.domain.bundle_manifest import compatibility_warnings
from app.services.bundle_archive import DEFAULT_LIMITS, ArchiveLimits
from app.services.bundle_import import apply_bundle
from app.services.bundle_io import LoadedBundle, load_bundle
from app.services.bundle_source import same_source
from app.services.site_backup import lexicon_version

PROJECT_FORMATS = frozenset({"pandawords.project"})
UPLOAD_NAME = "upload.tar.gz"


async def _private_dir(settings: Settings) -> Path:
    work_dir = settings.bundle_work_dir
    if work_dir is not None:
        await asyncio.to_thread(work_dir.mkdir, parents=True, exist_ok=True)
    path = await asyncio.to_thread(tempfile.mkdtemp, prefix="pandawords-import-", dir=work_dir)
    return Path(path)


async def receive_upload(chunks: AsyncIterator[bytes], directory: Path, limit: int) -> Path:
    """Stream the request body to ``directory``; stop as soon as ``limit`` is exceeded."""
    path = directory / UPLOAD_NAME
    stream: IO[bytes] = await asyncio.to_thread(path.open, "xb")
    size = 0
    try:
        async for chunk in chunks:
            size += len(chunk)
            if size > limit:
                raise BundleError("too_large", "upload", status=413)
            await asyncio.to_thread(stream.write, chunk)
    finally:
        await asyncio.to_thread(stream.close)
    if size == 0:
        raise BundleError("empty_upload", "upload")
    return path


async def _warnings(settings: Settings, bundle: LoadedBundle) -> list[str]:
    manifest = bundle.archive.manifest
    lexicon = await lexicon_version(settings) if manifest.lexicon_version else None
    return compatibility_warnings(
        manifest,
        lexicon_version=lexicon,
        source_lang=settings.source_language,
        target_lang=settings.target_language,
    )


async def import_project(
    db: AsyncSurrealConnection,
    settings: Settings,
    owner: str,
    chunks: AsyncIterator[bytes],
    include_progress: bool | None,
) -> ImportSummary:
    """``include_progress=None`` means: on only for a verified same-user restore."""
    directory = await _private_dir(settings)
    bundle: LoadedBundle | None = None
    try:
        limit = settings.bundle_import_max_bytes
        upload = await receive_upload(chunks, directory, limit)
        limits = ArchiveLimits(
            max_entries=DEFAULT_LIMITS.max_entries,
            max_entry_bytes=min(DEFAULT_LIMITS.max_entry_bytes, 4 * limit),
            max_total_bytes=min(DEFAULT_LIMITS.max_total_bytes, 8 * limit),
            max_archive_bytes=limit,
        )
        bundle = await asyncio.to_thread(
            load_bundle,
            upload,
            directory,
            expected_formats=PROJECT_FORMATS,
            limits=limits,
        )
        same = same_source(settings, owner, bundle.archive.manifest)
        progress = same if include_progress is None else include_progress
        options = ImportOptions(progress, fallback_project=bundle.data.projects[0].ref)
        plan = await apply_bundle(db, settings, owner, bundle, options)
        return ImportSummary(
            project_ids=[encode_rid(project, "project") for project in plan.projects],
            progress_imported=progress,
            same_source=same,
            created=dict(sorted(plan.created.items())),
            merged=dict(sorted(plan.merged.items())),
            skipped=dict(sorted(plan.skipped.items())),
            conflicts=sorted(plan.notices),
            warnings=await _warnings(settings, bundle),
        )
    finally:
        if bundle is not None:
            await asyncio.to_thread(bundle.close)
        await asyncio.to_thread(shutil.rmtree, directory, ignore_errors=True)
