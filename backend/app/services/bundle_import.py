"""Generic bundle import core: validate media, then plan and apply rows + files atomically.

Reused by project import (6.1.3) and user restore (6.1.4). Rows are written in one SurrealDB
transaction; media files are copied into fresh random paths before commit and removed again
if anything fails (including commit), so a failed import leaves neither rows nor files.
"""

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import UUID

import structlog
from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.core.errors import AppError, BundleError
from app.db import bundle_import as repository
from app.db.auth import _atomic
from app.domain.bundle_import import ImportOptions, ImportPlan, allocate, check_size, state_query
from app.domain.bundle_import_plan import build_plan
from app.domain.identity import user_key
from app.domain.images import MAX_BYTES as MAX_IMAGE_BYTES
from app.services import image_validation
from app.services.bundle_io import LoadedBundle
from app.services.media import _file  # pyright: ignore[reportPrivateUsage]

logger = structlog.get_logger()
_CHUNK = 1024 * 1024
_AUDIO_MAGIC: dict[str, tuple[bytes, ...]] = {
    "audio/mpeg": (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3"),
    "audio/ogg": (b"OggS",),
    "audio/wav": (b"RIFF",),
    "audio/mp4": (),
    "audio/webm": (b"\x1a\x45\xdf\xa3",),
}


def _audio_ok(head: bytes, mime: str) -> bool:
    if mime == "audio/mp4":
        return head[4:8] == b"ftyp"
    if mime == "audio/wav" and head[8:12] != b"WAVE":
        return False
    prefixes = _AUDIO_MAGIC.get(mime, ())
    return bool(prefixes) and head.startswith(prefixes)


def validate_media_files(bundle: LoadedBundle, settings: Settings) -> None:
    """Reject empty/oversized files and content that does not match the declared type."""
    problems: list[str] = []
    checked: set[str] = set()
    for i, entry in enumerate(bundle.data.media):
        if entry.file in checked:
            continue
        checked.add(entry.file)
        path = bundle.media_path(entry.file)
        size = path.stat().st_size
        limit = MAX_IMAGE_BYTES if entry.kind == "image" else settings.audio_max_bytes
        if size == 0 or size > limit:
            problems.append(f"media_size: media[{i}]")
            continue
        if entry.kind == "image":
            try:
                image_validation.validate(path.read_bytes(), entry.mime)
            except AppError:
                problems.append(f"media_content: media[{i}]")
        else:
            with path.open("rb") as stream:
                if not _audio_ok(stream.read(16), entry.mime):
                    problems.append(f"media_content: media[{i}]")
    if problems:
        raise BundleError("invalid_media", "media", problems[:20])


def _copy_files(
    bundle: LoadedBundle, root: Path, files: list[tuple[str, str]], written: list[Path]
) -> None:
    for name, relative in files:
        target = _file(root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = _file(root, relative)
        with bundle.media_path(name).open("rb") as source, target.open("xb") as sink:
            written.append(target)
            shutil.copyfileobj(source, sink, _CHUNK)


def _remove(written: list[Path]) -> None:
    for path in written:
        path.unlink(missing_ok=True)
    written.clear()


async def apply_bundle(
    db: AsyncSurrealConnection,
    settings: Settings,
    owner: str,
    bundle: LoadedBundle,
    options: ImportOptions,
    finalize: Callable[[UUID, ImportPlan], Awaitable[None]] | None = None,
) -> ImportPlan:
    """Merge a fully validated bundle into ``owner``'s data; all-or-nothing.

    ``finalize`` runs inside the same transaction after the rows are written (user restore
    records preferences and its receipt there); raising from it rolls everything back.
    """
    user = RecordID("user", user_key(owner))
    check_size(bundle.data)
    await asyncio.to_thread(validate_media_files, bundle, settings)
    local = allocate(bundle.data)
    query = state_query(bundle.data, bundle.index, local)
    written: list[Path] = []

    async def operation(txn: UUID) -> ImportPlan:
        await asyncio.to_thread(_remove, written)  # files of a retried attempt
        state = await repository.read_state(db, user, query, txn)
        plan = build_plan(bundle.data, bundle.index, user, local, state, options)
        await asyncio.to_thread(_copy_files, bundle, settings.media_dir, plan.files, written)
        await repository.write_plan(db, user, plan, txn)
        if finalize is not None:
            await finalize(txn, plan)
        return plan

    try:
        return await _atomic(db, operation)
    except AppError:
        _remove(written)
        raise
    except Exception as exc:
        _remove(written)
        logger.warning("bundle_import_failed", stage="apply", error=type(exc).__name__)
        raise BundleError("apply_failed", "apply", status=500) from None
    except BaseException:
        _remove(written)
        raise
