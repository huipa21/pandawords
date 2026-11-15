"""Safe ``.tar.gz`` bundle read/write shared by project, user and site archives.

Writing streams members into a hidden temporary file beside the destination and publishes it
with an atomic rename, so a failed export never leaves a partial archive. Reading streams the
archive once, validates the manifest (and therefore the version) before extracting anything
else, and only extracts regular files with safe relative names into a private staging
directory, enforcing entry-count, per-entry and total-size limits and every sha256/size.
"""

import hashlib
import io
import os
import shutil
import tarfile
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import IO, Self

from app.core.errors import BundleError
from app.domain.bundle_manifest import (
    MANIFEST_FILE,
    MAX_MANIFEST_BYTES,
    Manifest,
    ManifestEntry,
    ManifestHeader,
    parse_manifest,
)

_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class ArchiveLimits:
    max_entries: int = 100_000
    max_entry_bytes: int = 512 * 1024 * 1024
    max_total_bytes: int = 4 * 1024 * 1024 * 1024
    max_archive_bytes: int = 4 * 1024 * 1024 * 1024


DEFAULT_LIMITS = ArchiveLimits()


@dataclass(frozen=True)
class ArchiveMember:
    """``source`` is in-memory bytes or a local file streamed into the archive."""

    name: str
    source: bytes | Path


def _digest(source: bytes | Path) -> tuple[str, int]:
    if isinstance(source, bytes):
        return hashlib.sha256(source).hexdigest(), len(source)
    digest, size = hashlib.sha256(), 0
    with source.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _info(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.mtime, info.type = size, 0o644, 0, tarfile.REGTYPE
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def write_archive(
    destination: Path,
    header: ManifestHeader,
    members: Iterable[ArchiveMember],
    limits: ArchiveLimits = DEFAULT_LIMITS,
    verify: Callable[[Manifest], None] | None = None,
) -> Manifest:
    """Write ``manifest.json`` first, then members sorted by name; publish atomically.

    ``verify`` runs against the final manifest before anything is written.
    """
    ordered = sorted(members, key=lambda member: member.name)
    if len(ordered) + 1 > limits.max_entries:
        raise BundleError("too_many_entries", "archive")
    entries: list[ManifestEntry] = []
    for member in ordered:
        sha256, size = _digest(member.source)
        if size > limits.max_entry_bytes:
            raise BundleError("entry_too_large", "archive")
        entries.append(ManifestEntry(path=member.name, sha256=sha256, size=size))
    manifest = Manifest(**header.model_dump(), entries=entries)
    raw = (manifest.model_dump_json() + "\n").encode()
    parse_manifest(raw)  # the writer never emits a bundle its own reader would reject
    if verify is not None:
        verify(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as raw_file:
            with tarfile.open(fileobj=raw_file, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
                tar.addfile(_info(MANIFEST_FILE, len(raw)), io.BytesIO(raw))
                for member, entry in zip(ordered, entries, strict=True):
                    if isinstance(member.source, bytes):
                        tar.addfile(_info(member.name, entry.size), io.BytesIO(member.source))
                    else:
                        with member.source.open("rb") as source:
                            tar.addfile(_info(member.name, entry.size), source)
            raw_file.flush()
            os.fsync(raw_file.fileno())
        os.replace(temp, destination)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return manifest


class OpenedArchive:
    """Validated, extracted archive; remove the staging directory with ``close()``."""

    def __init__(self, manifest: Manifest, root: Path) -> None:
        self.manifest = manifest
        self.root = root

    def path(self, name: str) -> Path:
        if name not in {entry.path for entry in self.manifest.entries}:
            raise BundleError("missing_entry", "archive")
        return self.root.joinpath(*name.split("/"))

    def read_bytes(self, name: str) -> bytes:
        return self.path(name).read_bytes()

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def _copy(source: IO[bytes], target: Path, entry: ManifestEntry) -> None:
    digest, size = hashlib.sha256(), 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        while chunk := source.read(_CHUNK):
            size += len(chunk)
            if size > entry.size:
                raise BundleError("integrity", "archive", [entry.path])
            digest.update(chunk)
            handle.write(chunk)
    if size != entry.size or digest.hexdigest() != entry.sha256:
        raise BundleError("integrity", "archive", [entry.path])


def _safe_member(member: tarfile.TarInfo) -> None:
    name = member.name
    if (
        not member.isreg()
        or name.startswith(("/", "\\"))
        or "\\" in name
        or ":" in name
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        raise BundleError("unsafe_entry", "archive")


def _read_manifest(
    tar: tarfile.TarFile, limits: ArchiveLimits, expected: frozenset[str] | None
) -> Manifest:
    first = tar.next()
    if first is None or first.name != MANIFEST_FILE:
        raise BundleError("missing_manifest", "archive")
    _safe_member(first)
    if first.size > MAX_MANIFEST_BYTES:
        raise BundleError("manifest_too_large", "manifest")
    source = tar.extractfile(first)
    if source is None:
        raise BundleError("unsafe_entry", "archive")
    manifest = parse_manifest(source.read(MAX_MANIFEST_BYTES + 1), expected)
    if len(manifest.entries) + 1 > limits.max_entries:
        raise BundleError("too_many_entries", "archive")
    if sum(entry.size for entry in manifest.entries) > limits.max_total_bytes:
        raise BundleError("too_large", "archive")
    if any(entry.size > limits.max_entry_bytes for entry in manifest.entries):
        raise BundleError("entry_too_large", "archive")
    return manifest


def read_archive(
    source: Path,
    staging_parent: Path,
    *,
    expected_formats: frozenset[str] | None = None,
    limits: ArchiveLimits = DEFAULT_LIMITS,
) -> OpenedArchive:
    """Validate and extract ``source``; raises :class:`BundleError` and cleans up on failure."""
    if source.stat().st_size > limits.max_archive_bytes:
        raise BundleError("too_large", "archive")
    staging_parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=".bundle-", dir=staging_parent))
    try:
        with source.open("rb") as raw, tarfile.open(fileobj=raw, mode="r|gz") as tar:
            manifest = _read_manifest(tar, limits, expected_formats)
            expected = {entry.path: entry for entry in manifest.entries}
            seen: set[str] = set()
            while (member := tar.next()) is not None:
                _safe_member(member)
                entry = expected.get(member.name)
                if entry is None or member.name in seen or member.size != entry.size:
                    raise BundleError("unexpected_entry", "archive")
                seen.add(member.name)
                stream = tar.extractfile(member)
                if stream is None:
                    raise BundleError("unsafe_entry", "archive")
                _copy(stream, root.joinpath(*member.name.split("/")), entry)
        if seen != expected.keys():
            raise BundleError("missing_entry", "archive")
        return OpenedArchive(manifest, root)
    except BundleError:
        shutil.rmtree(root, ignore_errors=True)
        raise
    except (tarfile.TarError, EOFError, OSError, ValueError) as error:
        shutil.rmtree(root, ignore_errors=True)
        raise BundleError("malformed_archive", "archive") from error
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
