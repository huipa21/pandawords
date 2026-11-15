"""Build, verify and safely extract `pandawords.site` tar.gz archives (blocking I/O)."""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
import zlib
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import IO, BinaryIO

from pydantic import ValidationError

from app.domain.site_backup import SiteBackupFile, SiteBackupManifest

MANIFEST = "manifest.json"
DATABASE = "db.surql"
MEDIA_PREFIX = "media/"
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
_CHUNK = 1024 * 1024
# Transient restore/backup directories inside the media volume and secret-like files.
INTERNAL_MEDIA_PREFIXES = (".site-restore-", ".site-media-old-")
_SECRET_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".partial")


class ArchiveError(Exception):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def safe_relative(name: str) -> bool:
    if not name or len(name) > 1024 or "\\" in name or "\x00" in name or ":" in name:
        return False
    if name.startswith("/"):
        return False
    return all(part not in {"", ".", ".."} for part in name.split("/"))


def _excluded(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith(".env")
        or lowered.endswith(_SECRET_SUFFIXES)
        or name.startswith(INTERNAL_MEDIA_PREFIXES)
    )


def collect_media(media_dir: Path, excluded: list[Path]) -> list[tuple[Path, SiteBackupFile]]:
    """Regular files only; symlinks, secrets, excluded trees and restore leftovers are skipped."""
    if not media_dir.is_dir():
        return []
    root = media_dir.resolve()
    skip = {path.resolve() for path in excluded}
    found: list[tuple[Path, SiteBackupFile]] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        base = Path(current)
        dirs[:] = sorted(
            name
            for name in dirs
            if not _excluded(name)
            and not (base / name).is_symlink()
            and (base / name).resolve() not in skip
        )
        for name in sorted(files):
            path = base / name
            if _excluded(name) or path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if not safe_relative(relative):
                continue
            digest, size = sha256_file(path)
            found.append((path, SiteBackupFile(path=relative, size=size, sha256=digest)))
    return sorted(found, key=lambda item: item[1].path)


def _add_file(archive: tarfile.TarFile, name: str, path: Path, size: int, mtime: float) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.mtime = size, 0o600, mtime
    with path.open("rb") as stream:
        archive.addfile(info, stream)


def write_archive(
    target: Path,
    manifest: SiteBackupManifest,
    database: Path,
    media: list[tuple[Path, SiteBackupFile]],
) -> None:
    payload = manifest.model_dump_json(indent=2).encode("utf-8")
    mtime = manifest.created_at.timestamp()
    with tarfile.open(target, "x:gz") as archive:
        info = tarfile.TarInfo(MANIFEST)
        info.size, info.mode, info.mtime = len(payload), 0o600, mtime
        archive.addfile(info, io.BytesIO(payload))
        _add_file(archive, DATABASE, database, manifest.database.size, mtime)
        for path, entry in media:
            _add_file(archive, MEDIA_PREFIX + entry.path, path, entry.size, mtime)


def _manifest(archive: tarfile.TarFile) -> SiteBackupManifest:
    member = archive.next()
    if member is None or member.name != MANIFEST or not member.isfile():
        raise ArchiveError("manifest", "Archive must start with manifest.json")
    if member.size > MAX_MANIFEST_BYTES:
        raise ArchiveError("manifest", "manifest.json is too large")
    stream = archive.extractfile(member)
    if stream is None:
        raise ArchiveError("manifest", "manifest.json is unreadable")
    try:
        return SiteBackupManifest.model_validate_json(stream.read())
    except ValidationError as error:
        fields = sorted({".".join(str(part) for part in item["loc"]) for item in error.errors()})
        raise ArchiveError(
            "manifest", f"Unsupported or invalid site manifest: {', '.join(fields[:5])}"
        ) from None


def _expected(manifest: SiteBackupManifest) -> dict[str, tuple[int, str]]:
    expected = {DATABASE: (manifest.database.size, manifest.database.sha256)}
    for entry in manifest.media:
        name = MEDIA_PREFIX + entry.path
        if not safe_relative(entry.path) or name in expected:
            raise ArchiveError("manifest", "Manifest lists an unsafe or duplicate media path")
        expected[name] = (entry.size, entry.sha256)
    return expected


def _open_output(destination: Path | None) -> BinaryIO | None:
    if destination is None:
        return None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination.open("xb")
    except OSError as error:
        raise ArchiveError("extract", f"Cannot write staged file: {type(error).__name__}") from None


def _copy(source: IO[bytes], destination: Path | None, size: int) -> str:
    digest = hashlib.sha256()
    written = 0
    output = _open_output(destination)
    try:
        while chunk := source.read(_CHUNK):
            written += len(chunk)
            if written > size:
                break
            digest.update(chunk)
            if output is not None:
                try:
                    output.write(chunk)
                except OSError as error:
                    message = f"Cannot write staged file: {type(error).__name__}"
                    raise ArchiveError("extract", message) from None
    finally:
        if output is not None:
            output.close()
    if written != size:
        raise ArchiveError("integrity", "Archive entry size does not match its header")
    return digest.hexdigest()


def read_archive(
    path: Path,
    *,
    max_entries: int,
    max_bytes: int,
    destination: Callable[[str], Path | None] | None = None,
) -> SiteBackupManifest:
    """Verify every entry against the manifest; optionally stream entries to `destination`."""
    try:
        with tarfile.open(path, "r|gz") as archive:
            manifest = _manifest(archive)
            expected = _expected(manifest)
            if len(expected) + 1 > max_entries:
                raise ArchiveError("limits", "Archive has too many entries")
            if sum(size for size, _ in expected.values()) > max_bytes:
                raise ArchiveError("limits", "Archive expands beyond the configured limit")
            seen: set[str] = set()
            while (member := archive.next()) is not None:
                name = member.name
                if not safe_relative(name) or not member.isfile():
                    raise ArchiveError("unsafe_entry", "Archive contains an unsafe entry")
                if name not in expected or name in seen:
                    raise ArchiveError("unsafe_entry", "Archive contains an unexpected entry")
                size, digest = expected[name]
                if member.size != size:
                    raise ArchiveError("integrity", f"Size mismatch for {name}")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ArchiveError("integrity", f"Unreadable entry {name}")
                target = destination(name) if destination is not None else None
                if _copy(stream, target, size) != digest:
                    raise ArchiveError("integrity", f"Checksum mismatch for {name}")
                seen.add(name)
            if missing := sorted(set(expected) - seen):
                raise ArchiveError("integrity", f"Archive is missing {missing[0]}")
            return manifest
    except ArchiveError:
        raise
    except (tarfile.TarError, EOFError, zlib.error, OSError) as error:
        raise ArchiveError(
            "archive", f"Archive is corrupt or unreadable: {type(error).__name__}"
        ) from None


def contained(root: Path, relative: str) -> Path:
    """Resolve an already validated relative path and prove it stays inside `root`."""
    base = root.resolve()
    target = (base / PurePosixPath(relative)).resolve()
    if not target.is_relative_to(base) or target == base:
        raise ArchiveError("unsafe_entry", "Archive entry escapes its destination")
    return target
