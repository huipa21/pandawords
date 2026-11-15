"""Owner-filtered, bounded snapshot of one project for ``pandawords.project`` export.

Every read filters ``owner = NONE OR owner = $user`` (dictionary rows/edges and media) or
``owner = $user`` (project, memberships, overrides, notes, progress), and every edge must
also have visible endpoints, so another account's rows never enter the snapshot.
"""

from collections.abc import Iterable
from typing import Any, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.db.auth import _atomic, _rows
from app.domain.bundle_serialize import BundleSource
from app.domain.identity import user_key

MAX_MEMBERSHIPS = 10_000
MAX_RECORDS = 25_000
MAX_EDGES = 100_000
MAX_ATTACHED = 50_000
MAX_REVIEW_LOGS = 200_000
MAX_ROUNDS = 12

type Row = dict[str, Any]

# Exported sources pull in their targets along these edges (a lemma's lexemes, a lexeme's
# morphemes, tags, example sentences/phrases, passages). relates_to/derives_to/contains and a
# lexeme's unselected senses only join records that are already exported.
_PULL_SOURCES: dict[str, frozenset[str]] = {
    "has_lexeme": frozenset({"lemma"}),
    "composed_of": frozenset({"lexeme"}),
    "member_of": frozenset({"sense", "morpheme", "tag"}),
    "used_in": frozenset({"sense"}),
    "part_of": frozenset({"sentence"}),
}
# An exported child pulls in its parent: the lexeme of a sense and the lemma of a lexeme.
_PARENTS = frozenset({"has_sense", "has_lexeme"})
_EDGE_TABLES = frozenset(
    {"has_lexeme", "has_sense", "composed_of", "derives_to", "relates_to"}
    | {"member_of", "contains", "used_in", "part_of"}
)
_EDGE_FILTER = (
    "(owner = NONE OR owner = $user) AND (in.owner = NONE OR in.owner = $user) "
    "AND (out.owner = NONE OR out.owner = $user)"
)
_OUTGOING = f"SELECT ->(? WHERE {_EDGE_FILTER}).* AS edges FROM $records "
_INCOMING = f"SELECT <-(? WHERE {_EDGE_FILTER}).* AS edges FROM $records "
_VISIBLE = "WHERE owner = NONE OR owner = $user;"


def _too_large() -> AppError:
    return AppError("project.export_too_large", 413, "Project exceeds the export bounds.")


def _bounded[T](items: list[T], limit: int) -> list[T]:
    if len(items) > limit:
        raise _too_large()
    return items


class _Snapshot:
    def __init__(
        self,
        db: AsyncSurrealConnection,
        user: RecordID,
        txn: UUID,
        limits: tuple[int, int] = (MAX_RECORDS, MAX_EDGES),
    ) -> None:
        self.db, self.user, self.txn = db, user, txn
        self.max_records, self.max_edges = limits
        self.records: dict[RecordID, Row] = {}
        self.edges: dict[RecordID, Row] = {}

    async def rows(self, query: str, params: dict[str, Value]) -> list[Row]:
        return await _rows(self.db, query, {**params, "user": self.user}, txn_id=self.txn)

    async def add_records(self, ids: Iterable[RecordID]) -> list[RecordID]:
        wanted = [rid for rid in dict.fromkeys(ids) if rid not in self.records]
        if not wanted:
            return []
        found = await self.rows(
            "SELECT * FROM $records " + _VISIBLE, {"records": cast(Value, wanted)}
        )
        for row in found:
            self.records[row["id"]] = row
        _bounded(list(self.records), self.max_records)
        return [row["id"] for row in found]

    async def adjacent(self, frontier: list[RecordID]) -> list[Row]:
        params: dict[str, Value] = {"records": cast(Value, frontier)}
        found: list[Row] = []
        for query in (_OUTGOING, _INCOMING):
            for row in await self.rows(query + _VISIBLE, params):
                edges = cast(list[Row], row.get("edges") or [])
                found += [e for e in edges if e["id"].table_name in _EDGE_TABLES]
        for edge in found:
            self.edges[edge["id"]] = edge
        _bounded(list(self.edges), self.max_edges)
        return found

    def _pulled(self, edge: Row) -> RecordID | None:
        table = edge["id"].table_name
        start, end = edge["in"], edge["out"]
        if table in _PARENTS and end in self.records:
            return start
        if start in self.records and start.table_name in _PULL_SOURCES.get(table, ()):
            return end
        return None

    async def expand(self, seeds: list[RecordID]) -> None:
        frontier = await self.add_records(seeds)
        for _ in range(MAX_ROUNDS):
            if not frontier:
                return
            edges = await self.adjacent(frontier)
            pulled = [rid for edge in edges if (rid := self._pulled(edge)) is not None]
            frontier = await self.add_records(pulled)
        if frontier:
            raise _too_large()

    def kept_edges(self, selected: set[RecordID]) -> list[Row]:
        kept: list[Row] = []
        for edge in self.edges.values():
            start, end = edge["in"], edge["out"]
            if start not in self.records or end not in self.records:
                continue
            # A lexeme's unselected senses are not part of the project.
            if edge["id"].table_name == "has_sense" and end not in selected:
                continue
            kept.append(edge)
        return sorted(kept, key=lambda edge: str(edge["id"]))


def _memberships(rows: list[Row]) -> list[Row]:
    """One membership per target; a retained duplicate hidden edge keeps the target hidden."""
    merged: dict[RecordID, Row] = {}
    for row in sorted(rows, key=lambda r: (r["added_at"], str(r["id"]))):
        current = merged.get(row["out"])
        if current is None:
            merged[row["out"]] = dict(row)
            continue
        current["hidden"] = current["hidden"] or row["hidden"]
        if current.get("study_order") is None:
            current["study_order"] = row.get("study_order")
    return list(merged.values())


async def _snapshot(
    db: AsyncSurrealConnection, user: RecordID, project: RecordID, txn: UUID
) -> tuple[_Snapshot, list[Row], list[Row], set[RecordID]]:
    snap = _Snapshot(db, user, txn)
    projects = await snap.rows("SELECT * FROM $project WHERE owner = $user;", {"project": project})
    if not projects:
        raise AppError("project.not_found", 404, "Project not found.")
    includes = await snap.rows(
        "SELECT * FROM includes WHERE owner = $user AND in = $project "
        "AND (out.owner = NONE OR out.owner = $user) LIMIT $limit;",
        {"project": project, "limit": MAX_MEMBERSHIPS + 1},
    )
    includes = _memberships(_bounded(includes, MAX_MEMBERSHIPS))
    targets = [row["out"] for row in includes]
    selected = {rid for rid in targets if rid.table_name == "sense"}
    await snap.expand(targets)
    includes = [row for row in includes if row["out"] in snap.records]
    return snap, projects, includes, selected


async def _attached(snap: _Snapshot, project: RecordID, selected: set[RecordID]) -> BundleSource:
    records = sorted(snap.records, key=str)
    overlays = [RecordID("override", [snap.user, rid]) for rid in records]
    overrides = await snap.rows(
        "SELECT * FROM $overlays WHERE owner = $user;", {"overlays": cast(Value, overlays)}
    )
    notes = await snap.rows(
        "SELECT * FROM note WHERE owner = $user AND target IN $targets LIMIT $limit;",
        {"targets": cast(Value, [project, *records]), "limit": MAX_ATTACHED + 1},
    )
    audio = [
        pron["audio"]
        for rid in records
        if rid.table_name == "lexeme"
        for pron in snap.records[rid].get("pron") or []
        if isinstance(pron.get("audio"), RecordID)
    ]
    media = await snap.rows(
        "SELECT * FROM media WHERE target IN $targets AND (owner = NONE OR owner = $user) "
        "LIMIT $limit;",
        {"targets": cast(Value, records), "limit": MAX_ATTACHED + 1},
    )
    known = {row["id"] for row in media}
    if extra := [rid for rid in dict.fromkeys(audio) if rid not in known]:
        media += await snap.rows("SELECT * FROM $media " + _VISIBLE, {"media": cast(Value, extra)})
    memories = [RecordID("memory", [snap.user, sense]) for sense in sorted(selected, key=str)]
    memory = await snap.rows(
        "SELECT * FROM $memories WHERE owner = $user;", {"memories": cast(Value, memories)}
    )
    logs = await snap.rows(
        "SELECT * FROM review_log WHERE owner = $user AND memory IN $memories LIMIT $limit;",
        {"memories": cast(Value, [row["id"] for row in memory]), "limit": MAX_REVIEW_LOGS + 1},
    )
    return BundleSource(
        records=[snap.records[rid] for rid in records],
        edges=snap.kept_edges(selected),
        overrides=overrides,
        notes=_bounded(notes, MAX_ATTACHED),
        media=_bounded(media, MAX_ATTACHED + len(audio)),
        memory=memory,
        review_log=_bounded(logs, MAX_REVIEW_LOGS),
    )


async def load_project(db: AsyncSurrealConnection, owner: str, project: RecordID) -> BundleSource:
    """Read the owner's project and everything needed to resolve it in one transaction.

    Media rows keep their storage ``path`` for the service to hash and copy; the serializer
    never writes it to a bundle. ``media_sha256`` is left empty for the caller to fill.
    """

    async def operation(txn: UUID) -> BundleSource:
        user = RecordID("user", user_key(owner))
        snap, projects, includes, selected = await _snapshot(db, user, project, txn)
        source = await _attached(snap, project, selected)
        source.projects = projects
        source.includes = includes
        return source

    return await _atomic(db, operation)
