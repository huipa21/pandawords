"""Build an :class:`ImportPlan` from a validated bundle and the importer's existing state.

Rules: shared rows/edges merge by deterministic ID and are never rewritten; an ID occupied by
a user-owned row is a conflict. Owner-owned rows get the importer's fresh IDs (an owned lemma
whose text already exists for the importer or in the shared dictionary reuses that lemma).
Existing memory and overrides win; review logs never duplicate a completed attempt.
"""

from typing import Any
from uuid import uuid4

from fsrs import Card as FsrsCard
from fsrs import Rating
from pydantic import ValidationError
from surrealdb import RecordID

from app.core.errors import BundleError
from app.core.record_ids import encode_rid
from app.domain.bundle import BundleData
from app.domain.bundle_import import (
    ExistingState,
    ImportOptions,
    ImportPlan,
    Row,
    identity_conflict,
)
from app.domain.bundle_records import LemmaRecord, LexemeRecord
from app.domain.bundle_refs import shared_record
from app.domain.bundle_restore import RefResolver, edge_endpoints, entry_fields, shared_edge_id
from app.domain.bundle_user import MediaEntry, MemoryEntry, ReviewLogEntry
from app.domain.bundle_validate import BundleIndex
from app.domain.media import MIME_EXTENSIONS
from app.domain.overrides import EDITABLE_FIELDS, OverrideFields
from app.domain.srs import CardState, MemoryRead, ReviewReceipt, fingerprint


class _Planner:
    def __init__(
        self,
        data: BundleData,
        index: BundleIndex,
        user: RecordID,
        local: dict[str, RecordID],
        state: ExistingState,
    ) -> None:
        self.data, self.index, self.user, self.state = data, index, user, state
        self.local = dict(local)
        self.reused: set[str] = set()
        self.plan = ImportPlan()

    def resolve(self) -> RefResolver:
        return RefResolver(self.local)

    def check_identities(self) -> None:
        problems: list[str] = []
        for ref, record in self.index.records.items():
            rid = shared_record(ref) if record.owner == "shared" else None
            if rid is not None and self.state.shared.get(rid) is False:
                problems.append(f"shared_identity: {record.table}")
        for edge in self.data.edges:
            rid = shared_edge_id(edge) if edge.owner == "shared" else None
            if rid is not None and self.state.shared.get(rid) is False:
                problems.append(f"shared_identity: {edge.table}")
        lemmas = [r for r in self.index.records.values() if isinstance(r, LemmaRecord)]
        planned: dict[tuple[str, str], RecordID] = {}
        for record in sorted(lemmas, key=lambda r: r.owner != "shared"):
            key = (record.lang, record.text)
            existing = self.state.lemmas.get(key)
            if record.owner == "shared":
                rid = shared_record(record.ref)
                if rid in self.state.shared:
                    continue
                if (existing is not None and existing[0] != rid) or key in planned:
                    problems.append("lemma_identity: lemma")
                planned[key] = rid
            elif key in planned:
                self.local[record.ref] = planned[key]
                self.reused.add(record.ref)
            elif existing is not None and existing[1]:
                self.local[record.ref] = existing[0]
                self.reused.add(record.ref)
            elif existing is not None:
                problems.append("lemma_identity: lemma")
            else:
                planned[key] = self.local[record.ref]
        if problems:
            raise identity_conflict(problems)

    def media(self) -> None:
        for entry in self.data.media:
            if entry.owner == "shared" and shared_record(entry.target) in self.state.shared:
                # The existing shared row keeps its own audio; nothing to import.
                self.local.pop(entry.ref, None)
                self.plan.skipped["media"] += 1
        resolve = self.resolve()
        for entry in self.data.media:
            if entry.ref in self.local:
                self._media(entry, resolve)

    def _media(self, entry: MediaEntry, resolve: RefResolver) -> None:
        rid = self.local[entry.ref]
        path = f"{entry.kind}/{rid.id}{MIME_EXTENSIONS[entry.kind][entry.mime]}"
        # Bundle media is always stored as the importer's own, even if it was shared audio.
        row = {**entry_fields(entry, resolve), "id": rid, "owner": self.user, "path": path}
        self.plan.rows.append(row)
        self.plan.files.append((entry.file, path))
        self.plan.created["media"] += 1

    def records(self) -> None:
        resolve = self.resolve()
        for ref, record in self.index.records.items():
            shared = record.owner == "shared"
            if (shared and shared_record(ref) in self.state.shared) or ref in self.reused:
                self.plan.merged["records"] += 1
                continue
            if isinstance(record, LexemeRecord):
                pron = [
                    p.model_copy(update={"audio": None})
                    if shared or p.audio is None or p.audio not in self.local
                    else p
                    for p in record.pron
                ]
                record = record.model_copy(update={"pron": pron})
            rid = shared_record(ref) if shared else self.local[ref]
            owner = None if shared else self.user
            self.plan.rows.append({**entry_fields(record, resolve), "id": rid, "owner": owner})
            self.plan.created["shared_records" if shared else "records"] += 1

    def edges(self) -> None:
        resolve = self.resolve()
        for edge in self.data.edges:
            start, end = edge_endpoints(edge, resolve)
            if edge.owner == "shared":
                rid = shared_edge_id(edge)
                if rid in self.state.shared:
                    self.plan.merged["edges"] += 1
                    continue
                owner = None
            else:
                rid, owner = RecordID(edge.table, uuid4().hex), self.user
            fields = entry_fields(edge, resolve)
            self.plan.edges.append({**fields, "id": rid, "in": start, "out": end, "owner": owner})
            self.plan.created["shared_edges" if owner is None else "edges"] += 1
            self.plan.touches_tags |= edge.table == "member_of"

    def projects(self) -> None:
        resolve = self.resolve()
        for project in self.data.projects:
            rid = self.local[project.ref]
            values = entry_fields(project, resolve)
            self.plan.rows.append({**values, "id": rid, "owner": self.user})
            self.plan.projects.append(rid)
            self.plan.created["projects"] += 1
        for include in self.data.includes:
            values = entry_fields(include, resolve)
            start, end = values.pop("project"), values.pop("target")
            rid = RecordID("includes", uuid4().hex)
            edge = {**values, "id": rid, "in": start, "out": end, "owner": self.user}
            self.plan.edges.append(edge)
            self.plan.created["memberships"] += 1

    def overlays(self) -> None:
        resolve = self.resolve()
        for override in self.data.overrides:
            target = resolve(override.target)
            allowed = EDITABLE_FIELDS[target.table_name]  # pyright: ignore[reportArgumentType]
            try:
                OverrideFields.model_validate(override.fields)
            except ValidationError:
                raise BundleError("override_field", "references", ["overrides"]) from None
            if not override.fields.keys() <= allowed:
                raise BundleError("override_field", "references", ["overrides"])
            if target in self.state.overrides or override.target in self.reused:
                self.plan.skipped["overrides"] += 1
                self.plan.notices.add("override_kept")
                continue
            self.plan.rows.append(
                {
                    "id": RecordID("override", [self.user, target]),
                    "owner": self.user,
                    "fields": dict(override.fields),
                    "updated_at": override.updated_at,
                }
            )
            self.plan.created["overrides"] += 1
        for note in self.data.notes:
            values = entry_fields(note, resolve)
            self.plan.rows.append({**values, "id": self.local[note.ref], "owner": self.user})
            self.plan.created["notes"] += 1

    def progress(self, options: ImportOptions) -> None:
        resolve = self.resolve()
        kept: set[str] = set()
        for memory in self.data.memory:
            sense = resolve(memory.sense)
            if sense in self.state.memories:
                kept.add(memory.sense)
                self.plan.skipped["memory"] += 1
                self.plan.notices.add("memory_kept")
                continue
            self.plan.rows.append(self._memory(memory, sense, options.include_progress))
            self.plan.created["memory"] += 1
        fallback = self.local.get(options.fallback_project) if options.fallback_project else None
        for log in self.data.review_log:
            project = resolve(log.project) if log.project is not None else fallback
            if (
                not options.include_progress
                or log.sense in kept
                or project is None
                or log.attempt_id in self.state.attempts
            ):
                self.plan.skipped["review_log"] += 1
                if options.include_progress and log.attempt_id in self.state.attempts:
                    self.plan.notices.add("review_log_duplicate")
                continue
            self.plan.logs.append(self._log(log, resolve(log.sense), project))
            self.plan.created["review_log"] += 1

    def _memory(self, memory: MemoryEntry, sense: RecordID, progress: bool) -> Row:
        if progress:
            card: dict[str, Any] = memory.card.model_dump()
        else:
            card = CardState.from_card(FsrsCard()).model_dump()
        return {
            "id": RecordID("memory", [self.user, sense]),
            "owner": self.user,
            "sense": sense,
            "introduced": memory.introduced and progress,
            **card,
        }

    def _log(self, log: ReviewLogEntry, sense: RecordID, project: RecordID) -> Row:
        memory = RecordID("memory", [self.user, sense])
        row: Row = {
            "id": RecordID("review_log", uuid4().hex),
            "owner": self.user,
            "memory": memory,
            "project": project,
            **log.model_dump(
                include={"exercise", "correct", "hint_used", "duration_ms", "auto_rating"}
                | {"rating", "at", "is_introduction", "attempt_id"}
            ),
        }
        if log.card_after is not None:
            receipt = ReviewReceipt(
                attempt_id=log.attempt_id,
                project_id=encode_rid(project, "project"),
                memory=MemoryRead(
                    id=encode_rid(memory, "memory"),
                    sense_id=encode_rid(sense, "sense"),
                    introduced=True,
                    card=CardState.model_validate(log.card_after.model_dump()),
                ),
                auto_rating=Rating(log.auto_rating),
                rating=Rating(log.rating),
                correct=log.correct,
                at=log.at,
                is_introduction=log.is_introduction,
            ).model_dump(mode="json")
            # Rebuilt receipt: optimizer-valid history, but never replayable as a new request.
            row["receipt"] = receipt
            row["request_fingerprint"] = fingerprint({"imported_receipt": receipt})
        return row


def build_plan(
    data: BundleData,
    index: BundleIndex,
    user: RecordID,
    local: dict[str, RecordID],
    state: ExistingState,
    options: ImportOptions,
) -> ImportPlan:
    planner = _Planner(data, index, user, local, state)
    planner.check_identities()
    planner.media()
    planner.records()
    planner.edges()
    planner.projects()
    planner.overlays()
    planner.progress(options)
    return planner.plan
