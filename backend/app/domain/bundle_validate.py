"""Cross-record validation of a schema-valid bundle; runs before any database or file write."""

import json
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.core.errors import BundleError, BundleStage
from app.domain.bundle import BundleData
from app.domain.bundle_edges import EDGE_ENDPOINTS
from app.domain.bundle_manifest import Manifest
from app.domain.bundle_records import DictRecord, LemmaRecord, LexemeRecord
from app.domain.bundle_refs import parse_ref
from app.domain.bundle_user import MediaEntry, NoteEntry, ProjectEntry
from app.domain.media import MIME_EXTENSIONS, TARGET_TABLES

MEMBERSHIP_TABLES = frozenset({"lemma", "lexeme", "sense", "sentence", "passage"})
_PROTECTED_OVERRIDE_KEYS = frozenset({"id", "owner", "in", "out"})
_MAX_PROBLEMS = 20


@dataclass
class BundleIndex:
    """Validated lookup tables an importer uses to resolve bundle references."""

    records: dict[str, DictRecord] = field(default_factory=dict)
    projects: dict[str, ProjectEntry] = field(default_factory=dict)
    notes: dict[str, NoteEntry] = field(default_factory=dict)
    media: dict[str, MediaEntry] = field(default_factory=dict)


class _Problems:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, code: str, where: str) -> None:
        if len(self.items) < _MAX_PROBLEMS:
            self.items.append(f"{code}: {where}")

    def raise_if_any(self, reason: str, stage: BundleStage) -> None:
        if self.items:
            raise BundleError(reason, stage, self.items)


def _local(ref: str, table: str) -> bool:
    try:
        parsed = parse_ref(ref)
    except ValueError:
        return False
    return parsed.table == table and not parsed.shared


def _index(data: BundleData, problems: _Problems) -> BundleIndex:
    index = BundleIndex()
    for i, record in enumerate(data.records):
        parsed = parse_ref(record.ref)
        if parsed.table != record.table:
            problems.add("ref_table", f"records[{i}]")
        if parsed.shared != (record.owner == "shared"):
            problems.add("owner_ref_mismatch", f"records[{i}]")
        if record.ref in index.records:
            problems.add("duplicate_ref", f"records[{i}]")
        index.records[record.ref] = record
    for name, items, table, store in (
        ("projects", data.projects, "project", index.projects),
        ("notes", data.notes, "note", index.notes),
        ("media", data.media, "media", index.media),
    ):
        for i, item in enumerate(items):
            if not _local(item.ref, table):
                problems.add("ref_table", f"{name}[{i}]")
            if item.ref in store:
                problems.add("duplicate_ref", f"{name}[{i}]")
            store[item.ref] = item  # pyright: ignore[reportArgumentType]
    return index


def _check_records(index: BundleIndex, problems: _Problems) -> None:
    for ref, record in index.records.items():
        if not isinstance(record, LexemeRecord):
            continue
        for pron in record.pron:
            media = index.media.get(pron.audio) if pron.audio is not None else None
            if pron.audio is not None and (media is None or media.kind != "audio"):
                problems.add("dangling_reference", f"{ref}.pron.audio")
            elif media is not None and record.owner == "shared" and media.owner != "shared":
                problems.add("owner_edge", f"{ref}.pron.audio")


def _check_edges(data: BundleData, index: BundleIndex, problems: _Problems) -> None:
    seen: set[str] = set()
    for i, edge in enumerate(data.edges):
        where = f"edges[{i}]"
        start, end = index.records.get(edge.from_), index.records.get(edge.to)
        if start is None or end is None:
            problems.add("dangling_reference", where)
            continue
        sources, targets = EDGE_ENDPOINTS[edge.table]
        if start.table not in sources or end.table not in targets:
            problems.add("edge_endpoint", where)
        if edge.owner == "shared" and "owned" in (start.owner, end.owner):
            problems.add("owner_edge", where)
        if edge.owner == "owned" and edge.identity:
            problems.add("owner_edge", where)
        if edge.table in {"relates_to", "member_of"} and edge.from_ == edge.to:
            problems.add("self_edge", where)
        phrase = start if edge.table == "contains" else end if edge.table == "used_in" else None
        if isinstance(phrase, LemmaRecord) and phrase.kind != "phrase":
            problems.add("edge_endpoint", where)
        identity = edge.model_dump(mode="json", by_alias=True)
        if edge.owner == "shared":
            identity = [edge.table, edge.from_, edge.to, edge.identity]
        key = json.dumps(identity, sort_keys=True, ensure_ascii=False)
        if key in seen:
            problems.add("duplicate_edge", where)
        seen.add(key)


def _check_overlays(data: BundleData, index: BundleIndex, problems: _Problems) -> None:
    pairs: set[tuple[str, str]] = set()
    for i, include in enumerate(data.includes):
        target = index.records.get(include.target)
        if include.project not in index.projects or target is None:
            problems.add("dangling_reference", f"includes[{i}]")
        elif target.table not in MEMBERSHIP_TABLES:
            problems.add("membership_target", f"includes[{i}]")
        if (include.project, include.target) in pairs:
            problems.add("duplicate_membership", f"includes[{i}]")
        pairs.add((include.project, include.target))
    targets: set[str] = set()
    for i, override in enumerate(data.overrides):
        if override.target not in index.records:
            problems.add("dangling_reference", f"overrides[{i}]")
        if override.target in targets:
            problems.add("duplicate_override", f"overrides[{i}]")
        if _PROTECTED_OVERRIDE_KEYS & override.fields.keys():
            problems.add("override_field", f"overrides[{i}]")
        targets.add(override.target)
    for i, note in enumerate(data.notes):
        if note.target not in index.records and note.target not in index.projects:
            problems.add("dangling_reference", f"notes[{i}]")


def _check_progress(data: BundleData, index: BundleIndex, problems: _Problems) -> None:
    senses: set[str] = set()
    for i, memory in enumerate(data.memory):
        record = index.records.get(memory.sense)
        if record is None or record.table != "sense":
            problems.add("dangling_reference", f"memory[{i}]")
        if memory.sense in senses:
            problems.add("duplicate_memory", f"memory[{i}]")
        senses.add(memory.sense)
    attempts: set[str] = set()
    for i, log in enumerate(data.review_log):
        if log.sense not in senses or (
            log.project is not None and log.project not in index.projects
        ):
            problems.add("dangling_reference", f"review_log[{i}]")
        if log.attempt_id in attempts:
            problems.add("duplicate_attempt", f"review_log[{i}]")
        attempts.add(log.attempt_id)


def _check_media(
    data: BundleData, index: BundleIndex, manifest: Manifest | None, problems: _Problems
) -> None:
    files = {entry.path for entry in manifest.entries} if manifest is not None else None
    used: set[str] = set()
    for i, media in enumerate(data.media):
        where = f"media[{i}]"
        target = index.records.get(media.target)
        if target is None or target.table not in TARGET_TABLES:
            problems.add("dangling_reference", where)
        elif media.owner == "shared" and (target.owner != "shared" or media.kind != "audio"):
            problems.add("owner_media", where)
        extension = MIME_EXTENSIONS[media.kind].get(media.mime)
        if extension is None or PurePosixPath(media.file).suffix != extension:
            problems.add("media_type", where)
        if media.accent is not None and media.kind != "audio":
            problems.add("media_accent", where)
        if files is not None and media.file not in files:
            problems.add("missing_media_file", where)
        used.add(media.file)
    if files is not None and any(p.startswith("media/") and p not in used for p in files):
        problems.add("unreferenced_media_file", "manifest.entries")


def validate_bundle(data: BundleData, manifest: Manifest | None = None) -> BundleIndex:
    """Raise :class:`BundleError` unless the bundle is internally consistent."""
    if data.format == "pandawords.site":
        raise BundleError("unexpected_format", "data", [data.format])
    if manifest is not None and (
        manifest.format != data.format or manifest.schema_revision != data.schema_revision
    ):
        raise BundleError("manifest_mismatch", "data")
    if data.format == "pandawords.project" and (
        len(data.projects) != 1 or data.preferences is not None
    ):
        raise BundleError("project_scope", "data")
    problems = _Problems()
    try:
        index = _index(data, problems)
    except ValueError:
        raise BundleError("invalid_reference", "references") from None
    _check_records(index, problems)
    _check_edges(data, index, problems)
    _check_overlays(data, index, problems)
    _check_progress(data, index, problems)
    problems.raise_if_any("invalid_references", "references")
    _check_media(data, index, manifest, problems)
    problems.raise_if_any("invalid_media", "media")
    if (
        manifest is not None
        and not manifest.attribution
        and any(record.owner == "shared" for record in data.records)
    ):
        raise BundleError("missing_attribution", "manifest")
    return index
