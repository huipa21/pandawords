"""Typed serializers from repository rows (SurrealDB SDK values) to bundle entries.

Repositories (6.1.2/6.1.4) load owner-filtered rows; this module only converts them. It
rejects rows owned by anyone other than the exporting user, drops storage-only fields
(media ``path``, receipts/fingerprints, revisions) and replaces every user-owned database ID
with a bundle-local reference.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError
from surrealdb import RecordID

from app.core.errors import BundleError
from app.domain.bundle import BundleData
from app.domain.bundle_edges import EDGE_MODELS
from app.domain.bundle_manifest import SCHEMA_REVISION, BundleFormat
from app.domain.bundle_records import RECORD_MODELS
from app.domain.bundle_refs import RefAllocator
from app.domain.bundle_user import (
    Card,
    IncludeEntry,
    MediaEntry,
    MemoryEntry,
    NoteEntry,
    OverrideEntry,
    Preferences,
    ProjectEntry,
    ReviewLogEntry,
)
from app.domain.media import MIME_EXTENSIONS

type Row = Mapping[str, Any]
_PREFERENCE_KEYS = (
    "theme",
    "locale",
    "accent",
    "desired_retention",
    "review_images_enabled",
    "review_audio_enabled",
)


@dataclass
class BundleSource:
    """Owner-filtered rows exactly as repositories return them."""

    records: Sequence[Row] = ()
    edges: Sequence[Row] = ()
    projects: Sequence[Row] = ()
    includes: Sequence[Row] = ()
    overrides: Sequence[Row] = ()
    notes: Sequence[Row] = ()
    media: Sequence[Row] = ()
    memory: Sequence[Row] = ()
    review_log: Sequence[Row] = ()
    user: Row | None = None
    media_sha256: Mapping[RecordID, str] = field(default_factory=dict[RecordID, str])


def _build[T: BaseModel](model: type[T], values: Mapping[str, Any], where: str) -> T:
    try:
        return model.model_validate(values)
    except ValidationError as error:
        problems = [
            f"{where}." + ".".join(str(part) for part in item["loc"]) + ": " + item["type"]
            for item in error.errors(include_url=False, include_input=False)[:20]
        ]
        raise BundleError("invalid_source", "data", problems) from None


class _Serializer:
    def __init__(self, owner: RecordID, source: BundleSource) -> None:
        self.owner = owner
        self.source = source
        rows = [*source.records, *source.projects, *source.notes, *source.media]
        self.refs = RefAllocator(owner, [(row["id"], row.get("owner")) for row in rows])

    def _own(self, row: Row, table: str) -> None:
        if row.get("owner") != self.owner:
            raise BundleError("foreign_owner", "references", [table])

    def _scope(self, row: Row) -> str:
        owner = row.get("owner")
        if owner is None:
            return "shared"
        if owner != self.owner:
            raise BundleError("foreign_owner", "references", [row["id"].table_name])
        return "owned"

    def _fields(self, row: Row, *drop: str) -> dict[str, Any]:
        return {k: v for k, v in row.items() if k not in {"id", "owner", *drop}}

    def record(self, row: Row) -> Any:
        record: RecordID = row["id"]
        values = self._fields(row)
        if "pron" in values:
            values["pron"] = [
                {**p, "audio": self.refs.ref(p["audio"]) if p.get("audio") else None}
                for p in values["pron"]
            ]
        model = RECORD_MODELS.get(record.table_name)
        if model is None:
            raise BundleError("unsupported_record", "data", [record.table_name])
        scope = self._scope(row)
        entry = {**values, "table": record.table_name, "ref": self.refs.ref(record)}
        return _build(model, {**entry, "owner": scope}, record.table_name)

    def edge(self, row: Row) -> Any:
        record: RecordID = row["id"]
        table = record.table_name
        model = EDGE_MODELS.get(table)
        if model is None:
            raise BundleError("unsupported_record", "data", [table])
        scope = self._scope(row)
        start, end = row["in"], row["out"]
        identity: list[Any] = []
        key = record.id
        if scope == "shared" and isinstance(key, list) and key[:2] == [start, end]:
            identity = list(key[2:])  # pyright: ignore[reportUnknownArgumentType]
        values = {
            **self._fields(row, "in", "out"),
            "table": table,
            "owner": scope,
            "from": self.refs.ref(start),
            "to": self.refs.ref(end),
            "identity": identity,
        }
        return _build(model, values, table)

    def project(self, row: Row) -> ProjectEntry:
        self._own(row, "project")
        values = self._fields(row, "srs_revision")
        return _build(ProjectEntry, {**values, "ref": self.refs.ref(row["id"])}, "project")

    def include(self, row: Row) -> IncludeEntry:
        self._own(row, "includes")
        values = {
            **self._fields(row, "in", "out"),
            "project": self.refs.ref(row["in"]),
            "target": self.refs.ref(row["out"]),
        }
        return _build(IncludeEntry, values, "includes")

    def override(self, row: Row) -> OverrideEntry:
        self._own(row, "override")
        key = row["id"].id
        if not isinstance(key, list) or len(key) != 2 or key[0] != self.owner:  # pyright: ignore[reportUnknownArgumentType]
            raise BundleError("foreign_owner", "references", ["override"])
        target = key[1]  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(target, RecordID):
            raise BundleError("invalid_source", "data", ["override"])
        target = self.refs.ref(target)
        return _build(OverrideEntry, {**self._fields(row), "target": target}, "override")

    def note(self, row: Row) -> NoteEntry:
        self._own(row, "note")
        values = {
            **self._fields(row),
            "ref": self.refs.ref(row["id"]),
            "target": self.refs.ref(row["target"]),
        }
        return _build(NoteEntry, values, "note")

    def media(self, row: Row) -> MediaEntry:
        record: RecordID = row["id"]
        scope = self._scope(row)
        digest = self.source.media_sha256.get(record)
        extension = MIME_EXTENSIONS.get(row.get("kind"), {}).get(row.get("mime", ""))  # pyright: ignore[reportCallIssue, reportArgumentType]
        if digest is None or extension is None:
            raise BundleError("missing_media_file", "media", ["media"])
        values = {
            **self._fields(row, "path"),
            "ref": self.refs.ref(record),
            "owner": scope,
            "target": self.refs.ref(row["target"]),
            "file": f"media/{digest}{extension}",
        }
        return _build(MediaEntry, values, "media")

    def _sense(self, memory: RecordID) -> str:
        key = memory.id
        if not isinstance(key, list) or len(key) != 2 or key[0] != self.owner:  # pyright: ignore[reportUnknownArgumentType]
            raise BundleError("foreign_owner", "references", ["memory"])
        sense = key[1]  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(sense, RecordID):
            raise BundleError("invalid_source", "data", ["memory"])
        return self.refs.ref(sense)

    def memory(self, row: Row) -> MemoryEntry:
        self._own(row, "memory")
        card = self._fields(row, "sense", "introduced")
        values = {"sense": self._sense(row["id"]), "card": card, "introduced": row["introduced"]}
        return _build(MemoryEntry, values, "memory")

    def review(self, row: Row) -> ReviewLogEntry:
        self._own(row, "review_log")
        project: RecordID = row["project"]
        receipt = row.get("receipt")
        card_after = None
        if isinstance(receipt, dict) and isinstance(receipt.get("memory"), dict):  # pyright: ignore[reportUnknownMemberType]
            card_after = _card(receipt["memory"].get("card"))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
        values = {
            **self._fields(row, "memory", "project", "receipt", "request_fingerprint"),
            "sense": self._sense(row["memory"]),
            "project": self.refs.ref(project) if self.refs.known(project) else None,
            "card_after": card_after,
        }
        return _build(ReviewLogEntry, values, "review_log")


def _card(value: object) -> Card | None:
    try:
        return Card.model_validate(value, strict=False)
    except ValidationError:
        return None


def preferences(user: Row) -> Preferences:
    prefs = user.get("prefs") or {}
    values = {key: prefs.get(key) for key in _PREFERENCE_KEYS if key in prefs}
    values |= {"source_lang": user.get("source_lang"), "target_lang": user.get("target_lang")}
    return _build(Preferences, values, "preferences")


def serialize_bundle(
    owner: RecordID, bundle_format: BundleFormat, source: BundleSource
) -> BundleData:
    """Convert one owner's rows; repeated calls with the same rows give equal results."""
    if bundle_format == "pandawords.site":
        raise BundleError("unexpected_format", "data", [bundle_format])
    s = _Serializer(owner, source)
    return BundleData(
        format=bundle_format,
        schema_revision=SCHEMA_REVISION,
        records=[s.record(row) for row in source.records],
        edges=[s.edge(row) for row in source.edges],
        projects=[s.project(row) for row in source.projects],
        includes=[s.include(row) for row in source.includes],
        overrides=[s.override(row) for row in source.overrides],
        notes=[s.note(row) for row in source.notes],
        media=[s.media(row) for row in source.media],
        memory=[s.memory(row) for row in source.memory],
        review_log=[s.review(row) for row in source.review_log],
        preferences=preferences(source.user) if source.user is not None else None,
    )
