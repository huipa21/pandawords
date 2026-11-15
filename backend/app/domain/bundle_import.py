"""Pure import core shared by project import (6.1.3) and user restore (6.1.4).

Flow: :func:`allocate` gives every bundle-local ref a fresh database ID; :func:`state_query`
lists what the importer must read inside its transaction; :func:`build_plan` (in
``bundle_import_plan``) turns the validated bundle plus that :class:`ExistingState` into
rows/edges/files to insert. Nothing here touches the database or the filesystem.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from surrealdb import RecordID

from app.core.errors import BundleError
from app.domain.bundle import BundleData
from app.domain.bundle_records import LemmaRecord
from app.domain.bundle_refs import parse_ref, shared_record
from app.domain.bundle_restore import RefResolver, shared_edge_id
from app.domain.bundle_validate import BundleIndex

type Row = dict[str, Any]
MAX_IMPORT_ITEMS = 500_000


@dataclass(frozen=True)
class ImportOptions:
    include_progress: bool
    # Bundle ref of the project that receives review logs whose project is ``null``.
    fallback_project: str | None = None


@dataclass
class StateQuery:
    shared: list[RecordID]
    lemma_keys: list[tuple[str, str]]
    memories: list[RecordID]
    attempts: list[str]
    overrides: list[RecordID]


@dataclass
class ExistingState:
    """Facts read inside the import transaction."""

    # Existing rows/edges at the bundle's shared IDs -> True when the row is shared.
    shared: dict[RecordID, bool] = field(default_factory=dict[RecordID, bool])
    # (lang, text) -> existing lemma ID and whether the importer may use it
    # (shared or own; ``lemma_lang_text`` is globally unique).
    lemmas: dict[tuple[str, str], tuple[RecordID, bool]] = field(
        default_factory=dict[tuple[str, str], tuple[RecordID, bool]]
    )
    # Senses with the importer's memory, completed attempt IDs, overridden targets.
    memories: set[RecordID] = field(default_factory=set[RecordID])
    attempts: set[str] = field(default_factory=set[str])
    overrides: set[RecordID] = field(default_factory=set[RecordID])


@dataclass
class ImportPlan:
    rows: list[Row] = field(default_factory=list[Row])  # INSERT (any table, explicit ids)
    edges: list[Row] = field(default_factory=list[Row])  # INSERT RELATION after rows
    logs: list[Row] = field(default_factory=list[Row])  # review_log rows, after memory
    # (bundle file, media path) pairs to copy.
    files: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    projects: list[RecordID] = field(default_factory=list[RecordID])
    touches_tags: bool = False
    created: Counter[str] = field(default_factory=Counter[str])
    merged: Counter[str] = field(default_factory=Counter[str])
    skipped: Counter[str] = field(default_factory=Counter[str])
    notices: set[str] = field(default_factory=set[str])


class ImportSummary(BaseModel):
    """Completion result; counts only, never IDs of other accounts or storage paths."""

    project_ids: list[str]
    progress_imported: bool
    same_source: bool
    created: dict[str, int]
    merged: dict[str, int]
    skipped: dict[str, int]
    conflicts: list[str]
    warnings: list[str]


def identity_conflict(problems: list[str]) -> BundleError:
    return BundleError("identity_conflict", "apply", sorted(set(problems))[:20], status=409)


def check_size(data: BundleData) -> None:
    total = sum(
        len(items)
        for items in (
            data.records,
            data.edges,
            data.projects,
            data.includes,
            data.overrides,
            data.notes,
            data.media,
            data.memory,
            data.review_log,
        )
    )
    if total > MAX_IMPORT_ITEMS:
        raise BundleError("too_large", "data", status=413)


def allocate(data: BundleData) -> dict[str, RecordID]:
    """Fresh random IDs for every owner-owned row, project, note and media ref."""
    local: dict[str, RecordID] = {}
    for item in (*data.records, *data.projects, *data.notes, *data.media):
        parsed = parse_ref(item.ref)
        if not parsed.shared:
            local[item.ref] = RecordID(parsed.table, uuid4().hex)
    return local


def state_query(data: BundleData, index: BundleIndex, local: dict[str, RecordID]) -> StateQuery:
    resolve = RefResolver(local)
    shared = [shared_record(ref) for ref, row in index.records.items() if row.owner == "shared"]
    shared += [shared_edge_id(edge) for edge in data.edges if edge.owner == "shared"]
    lemmas = [
        (row.lang, row.text) for row in index.records.values() if isinstance(row, LemmaRecord)
    ]
    return StateQuery(
        shared=shared,
        lemma_keys=list(dict.fromkeys(lemmas)),
        memories=[resolve(memory.sense) for memory in data.memory],
        attempts=[log.attempt_id for log in data.review_log],
        overrides=[resolve(override.target) for override in data.overrides],
    )
