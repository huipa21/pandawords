"""One-call bundle export/load built on the archive helpers, data contract and validator."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import BundleError
from app.domain.bundle import BundleData, dump_data, parse_data
from app.domain.bundle_manifest import DATA_FILE, Manifest, ManifestHeader
from app.domain.bundle_validate import BundleIndex, validate_bundle
from app.services.bundle_archive import (
    DEFAULT_LIMITS,
    ArchiveLimits,
    ArchiveMember,
    OpenedArchive,
    read_archive,
    write_archive,
)


@dataclass
class LoadedBundle:
    archive: OpenedArchive
    data: BundleData
    index: BundleIndex

    def media_path(self, file: str) -> Path:
        return self.archive.path(file)

    def close(self) -> None:
        self.archive.close()


def export_bundle(
    destination: Path,
    header: ManifestHeader,
    data: BundleData,
    media_files: Mapping[str, Path],
    limits: ArchiveLimits = DEFAULT_LIMITS,
) -> Manifest:
    """Validate then atomically write ``data`` plus the media files named by its entries.

    ``media_files`` maps each bundle ``file`` (``media/<sha256><ext>``) to a readable local
    file; unreferenced files are not written.
    """
    if header.format != data.format:
        raise BundleError("manifest_mismatch", "manifest")
    validate_bundle(data)
    wanted = sorted({media.file for media in data.media})
    missing = [name for name in wanted if name not in media_files]
    if missing:
        raise BundleError("missing_media_file", "media", missing[:20])
    members = [ArchiveMember(DATA_FILE, dump_data(data))]
    members += [ArchiveMember(name, media_files[name]) for name in wanted]

    def verify(manifest: Manifest) -> None:
        _content_addressed(manifest)
        validate_bundle(data, manifest)

    return write_archive(destination, header, members, limits, verify)


def _content_addressed(manifest: Manifest) -> None:
    for entry in manifest.entries:
        if entry.path.startswith("media/") and not entry.path.startswith(f"media/{entry.sha256}."):
            raise BundleError("integrity", "media", [entry.path])


def load_bundle(
    source: Path,
    staging_parent: Path,
    *,
    expected_formats: frozenset[str],
    limits: ArchiveLimits = DEFAULT_LIMITS,
) -> LoadedBundle:
    """Fully validate an uploaded archive before the caller performs any database write."""
    archive = read_archive(source, staging_parent, expected_formats=expected_formats, limits=limits)
    try:
        data = parse_data(archive.read_bytes(DATA_FILE))
        _content_addressed(archive.manifest)
        index = validate_bundle(data, archive.manifest)
        return LoadedBundle(archive, data, index)
    except BaseException:
        archive.close()
        raise
