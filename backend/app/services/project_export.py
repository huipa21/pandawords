"""Project bundle export: owner snapshot -> hashed media -> validated archive in a private dir.

The archive is written to a fresh private directory (never into the media volume) and
published there atomically by ``export_bundle``; callers stream it and then call
:meth:`ProjectArchive.cleanup`. Any failure removes the directory before re-raising.
"""

import asyncio
import hashlib
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.db import project_export as repository
from app.domain.bundle import dump_data
from app.domain.bundle_manifest import ManifestHeader
from app.domain.bundle_serialize import BundleSource, serialize_bundle
from app.domain.media import MIME_EXTENSIONS
from app.services.bundle_io import export_bundle
from app.services.bundle_source import fingerprint
from app.services.media import _file  # pyright: ignore[reportPrivateUsage]
from app.services.projects import _project_id  # pyright: ignore[reportPrivateUsage]

logger = structlog.get_logger()
PROJECT_FORMAT = "pandawords.project"
ATTRIBUTION = ["Wiktionary (CC BY-SA)", "Open English WordNet (CC BY 4.0)", "ECDICT (MIT)"]
_CHUNK = 1024 * 1024
_UNSAFE_NAME = re.compile(r"[^\w\- ]+")


@dataclass
class ProjectArchive:
    path: Path
    filename: str
    skipped_media: int

    def cleanup(self) -> None:
        shutil.rmtree(self.path.parent, ignore_errors=True)


@dataclass
class _MediaFiles:
    sha256: dict[RecordID, str]
    files: dict[str, Path]
    skipped: set[RecordID]


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _media_files(root: Path, rows: Sequence[Mapping[str, Any]]) -> _MediaFiles:
    """Hash each readable stored file; missing/unreadable/unsafe files are skipped."""
    result = _MediaFiles({}, {}, set())
    for row in rows:
        extension = MIME_EXTENSIONS.get(row.get("kind"), {}).get(row.get("mime", ""))  # pyright: ignore[reportCallIssue, reportArgumentType]
        try:
            path = _file(root, row["path"])
            if extension is None or not path.is_file():
                raise FileNotFoundError
            digest = _digest(path)
        except OSError, ValueError:
            result.skipped.add(row["id"])
            continue
        result.sha256[row["id"]] = digest
        result.files[f"media/{digest}{extension}"] = path
    return result


def _without_skipped(source: BundleSource, media: _MediaFiles) -> BundleSource:
    def record(row: dict[str, Any]) -> dict[str, Any]:
        pron = row.get("pron")
        if not pron or not any(p.get("audio") in media.skipped for p in pron):
            return row
        audio = [{**p, "audio": None} if p.get("audio") in media.skipped else p for p in pron]
        return {**row, "pron": audio}

    source.records = [record(dict(row)) for row in source.records]
    source.media = [row for row in source.media if row["id"] not in media.skipped]
    source.media_sha256 = media.sha256
    return source


def _filename(name: str) -> str:
    stem = " ".join(_UNSAFE_NAME.sub("", name).split())[:60] or "project"
    return f"{stem}.pandawords-project.tar.gz"


def _write(
    settings: Settings, subject: str, owner: RecordID, source: BundleSource, directory: Path
) -> ProjectArchive:
    media = _media_files(settings.media_dir, source.media)
    source = _without_skipped(source, media)
    data = serialize_bundle(owner, PROJECT_FORMAT, source)
    project = source.projects[0]
    shared = any(item.owner == "shared" for item in [*data.records, *data.edges, *data.media])
    header = ManifestHeader(
        format=PROJECT_FORMAT,
        app_version=settings.app_version,
        created_at=datetime.now(UTC),
        source_lang=project["source_lang"],
        target_lang=project["target_lang"],
        attribution=ATTRIBUTION if shared else [],
        source=fingerprint(settings, subject, hashlib.sha256(dump_data(data)).hexdigest()),
    )
    path = directory / "project.tar.gz"
    export_bundle(path, header, data, media.files)
    return ProjectArchive(path, _filename(project["name"]), len(media.skipped))


async def export_project(
    db: AsyncSurrealConnection, settings: Settings, owner: str, project_id: str
) -> ProjectArchive:
    """Build a validated ``pandawords.project`` archive; the caller must call ``cleanup``."""
    project = _project_id(project_id)
    source = await repository.load_project(db, owner, project)
    owner_record = source.projects[0]["owner"]
    work_dir = settings.bundle_work_dir
    if work_dir is not None:
        await asyncio.to_thread(work_dir.mkdir, parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="pandawords-export-", dir=work_dir))
    try:
        archive = await asyncio.to_thread(_write, settings, owner, owner_record, source, directory)
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, directory, ignore_errors=True)
        logger.warning("project_export_failed", stage="archive")
        raise
    if archive.skipped_media:
        logger.warning("project_export_media_skipped", count=archive.skipped_media)
    return archive
