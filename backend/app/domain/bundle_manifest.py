"""Archive manifest contract and version/compatibility rules shared by all three formats."""

import json
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from app.core.errors import BundleError
from app.domain.bundle_edges import Entry, Instant, Lang, Short
from app.domain.bundle_user import SHA256_PATTERN

type BundleFormat = Literal["pandawords.project", "pandawords.user", "pandawords.site"]

FORMAT_VERSION = 1
"""Major format version. Readers reject any other major version before reading data."""
SCHEMA_REVISION = 1
"""Additive revision of ``data.json`` within the major version; newer revisions are rejected
because they may carry fields this reader would otherwise drop."""
DATA_FILE = "data.json"
MANIFEST_FILE = "manifest.json"
SITE_DB_FILE = "db.surql"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
ENTRY_PATTERN = (
    r"^(?:data\.json|db\.surql"
    r"|media/[0-9a-f]{64}\.(?:mp3|ogg|wav|m4a|webm|jpg|png|webp|gif)"
    r"|media/(?:[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*/){1,8}[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*)$"
)


class ManifestEntry(Entry):
    path: Annotated[str, Field(pattern=ENTRY_PATTERN, max_length=512)]
    sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    size: Annotated[int, Field(ge=0, lt=2**63)]


class ManifestHeader(Entry):
    """Everything in the manifest except the integrity list computed by the archive writer."""

    format: BundleFormat
    version: int = FORMAT_VERSION
    schema_revision: int = SCHEMA_REVISION
    app_version: Short
    created_at: Instant
    lexicon_version: Short | None = None
    source_lang: Lang
    target_lang: Lang
    attribution: Annotated[list[Short], Field(max_length=64)] = []
    # Keyed HMAC binding the exporting account to this data.json; only the issuing server can
    # verify it, and it identifies nobody without that server's secret.
    source: Annotated[str, Field(pattern=SHA256_PATTERN)] | None = None


class Manifest(ManifestHeader):
    entries: Annotated[list[ManifestEntry], Field(max_length=200_000)]


def _problems(error: ValidationError) -> list[str]:
    return [
        ".".join(str(part) for part in item["loc"]) + ": " + item["type"]
        for item in error.errors(include_url=False, include_input=False)[:20]
    ]


def parse_manifest(raw: bytes, expected: frozenset[str] | None = None) -> Manifest:
    """Check version first so incompatible majors fail with an explicit reason."""
    if len(raw) > MAX_MANIFEST_BYTES:
        raise BundleError("manifest_too_large", "manifest")
    try:
        probe = json.loads(raw)
    except ValueError, RecursionError:
        raise BundleError("malformed_manifest", "manifest") from None
    if not isinstance(probe, dict):
        raise BundleError("malformed_manifest", "manifest")
    version = probe.get("version")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if type(version) is not int:
        raise BundleError("malformed_manifest", "manifest", ["version: missing"])
    if version != FORMAT_VERSION:
        raise BundleError("unsupported_version", "manifest", [f"version: {version}"])
    revision = probe.get("schema_revision")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if type(revision) is int and revision > SCHEMA_REVISION:
        raise BundleError("unsupported_schema", "manifest", [f"schema_revision: {revision}"])
    try:
        manifest = Manifest.model_validate_json(raw)
    except ValidationError as error:
        raise BundleError("malformed_manifest", "manifest", _problems(error)) from None
    if manifest.schema_revision < 1:
        raise BundleError("unsupported_schema", "manifest")
    if expected is not None and manifest.format not in expected:
        raise BundleError("unexpected_format", "manifest", [manifest.format])
    check_entries(manifest)
    return manifest


def check_entries(manifest: Manifest) -> None:
    paths = [entry.path for entry in manifest.entries]
    if len(set(paths)) != len(paths):
        raise BundleError("duplicate_entry", "manifest")
    names = set(paths)
    if manifest.format == "pandawords.site":
        if SITE_DB_FILE not in names or DATA_FILE in names:
            raise BundleError("missing_entry", "manifest", [SITE_DB_FILE])
    elif DATA_FILE not in names or SITE_DB_FILE in names:
        raise BundleError("missing_entry", "manifest", [DATA_FILE])
    elif any(
        path.startswith("media/") and path.count("/") != 1 for path in names
    ):  # user/project media are content-addressed and flat
        raise BundleError("unsafe_entry", "manifest")


def compatibility_warnings(
    manifest: Manifest, *, lexicon_version: str | None, source_lang: str, target_lang: str
) -> list[str]:
    """Non-fatal differences an importer should report; never blocks a compatible bundle."""
    warnings: list[str] = []
    if manifest.lexicon_version != lexicon_version:
        warnings.append("lexicon_version")
    if manifest.source_lang.lower() != source_lang.lower():
        warnings.append("source_lang")
    if manifest.target_lang.lower() != target_lang.lower():
        warnings.append("target_lang")
    return warnings
