"""Owner-filtered, bounded snapshot of all of one user's data for ``pandawords.user`` backup.

Seeds are every owned project membership target, owned dictionary-like row, owned edge
endpoint, memory sense, override/note/media target; the project-export expansion then adds the
shared dictionary subset needed to resolve them. Every read filters ``owner = $user`` (or
``owner = NONE OR owner = $user`` for dictionary rows/edges/media), so another account's rows
never enter the snapshot. Account fields other than preferences are never read.
"""

from typing import Any, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.db.auth import _atomic
from app.db.project_export import (
    _memberships,  # pyright: ignore[reportPrivateUsage]
    _Snapshot,  # pyright: ignore[reportPrivateUsage]
)
from app.domain.bundle_serialize import BundleSource
from app.domain.identity import user_key

MAX_PROJECTS = 1_000
MAX_MEMBERSHIPS = 100_000
MAX_RECORDS = 100_000
MAX_EDGES = 400_000
MAX_ATTACHED = 100_000
MAX_REVIEW_LOGS = 500_000

type Row = dict[str, Any]

# Constant table names only; no caller input is ever formatted into these queries.
_RECORD_TABLES = ("lemma", "lexeme", "sense", "morpheme", "tag", "sentence", "passage")
_EDGE_TABLES = (
    "has_lexeme",
    "has_sense",
    "composed_of",
    "derives_to",
    "relates_to",
    "member_of",
    "contains",
    "used_in",
    "part_of",
)
_OWNED_IDS = {t: f"SELECT id FROM {t} WHERE owner = $user LIMIT $limit;" for t in _RECORD_TABLES}
_OWNED_ENDS = {t: f"SELECT in, out FROM {t} WHERE owner = $user LIMIT $limit;" for t in _EDGE_TABLES}
_VISIBLE = "WHERE owner = NONE OR owner = $user;"


def _override_target(row: Row) -> object:
    key = row["id"].id
    return key[1] if isinstance(key, list) and len(key) == 2 else None  # pyright: ignore[reportUnknownVariableType]


def _too_large() -> AppError:
    return AppError("backup.export_too_large", 413, "Your data exceeds the backup bounds.")


class _UserSnapshot:
    def __init__(self, db: AsyncSurrealConnection, user: RecordID, txn: UUID) -> None:
        self.snap = _Snapshot(db, user, txn, (MAX_RECORDS, MAX_EDGES))

    async def rows(self, query: str, limit: int, **params: Value) -> list[Row]:
        found = await self.snap.rows(query, {**params, "limit": limit + 1})
        if len(found) > limit:
            raise _too_large()
        return found

    async def seeds(self, *groups: list[Row]) -> list[RecordID]:
        seeds: list[RecordID] = []
        for query in _OWNED_IDS.values():
            seeds += [row["id"] for row in await self.rows(query, MAX_RECORDS)]
        for query in _OWNED_ENDS.values():
            for edge in await self.rows(query, MAX_EDGES):
                seeds += [edge["in"], edge["out"]]
        for group in groups:
            for row in group:
                target = row.get("target", row.get("out", row.get("sense")))
                if row["id"].table_name == "override":
                    target = _override_target(row)
                if isinstance(target, RecordID) and target.table_name != "project":
                    seeds.append(target)
        return seeds


async def _load(db: AsyncSurrealConnection, user: RecordID, txn: UUID) -> BundleSource:
    u = _UserSnapshot(db, user, txn)
    accounts = await u.rows(
        "SELECT prefs, source_lang, target_lang FROM $user WHERE id = $user;", 1, user=user
    )
    if not accounts:
        raise AppError("auth.user_not_found", 404, "User not found.")
    projects = await u.rows(
        "SELECT * FROM project WHERE owner = $user LIMIT $limit;", MAX_PROJECTS
    )
    includes = await u.rows(
        "SELECT * FROM includes WHERE owner = $user AND in.owner = $user "
        "AND (out.owner = NONE OR out.owner = $user) LIMIT $limit;",
        MAX_MEMBERSHIPS,
    )
    memory = await u.rows("SELECT * FROM memory WHERE owner = $user LIMIT $limit;", MAX_RECORDS)
    overrides = await u.rows(
        "SELECT * FROM override WHERE owner = $user LIMIT $limit;", MAX_ATTACHED
    )
    notes = await u.rows("SELECT * FROM note WHERE owner = $user LIMIT $limit;", MAX_ATTACHED)
    owned_media = await u.rows(
        "SELECT * FROM media WHERE owner = $user LIMIT $limit;", MAX_ATTACHED
    )
    seeds = await u.seeds(includes, memory, overrides, notes, owned_media)
    try:
        await u.snap.expand(list(dict.fromkeys(seeds)))
    except AppError as error:
        if error.code == "project.export_too_large":
            raise _too_large() from None
        raise
    records = u.snap.records
    known = set(records) | {row["id"] for row in projects}
    by_project: dict[RecordID, list[Row]] = {}
    for row in includes:
        if row["out"] in records:
            by_project.setdefault(row["in"], []).append(row)
    selected = {rid for rid in records if rid.table_name == "sense"}
    media = await _media(u, [*owned_media], sorted(records, key=str))
    memory = [row for row in memory if row["sense"] in records]
    logs = await u.rows(
        "SELECT * FROM review_log WHERE owner = $user AND memory IN $memories LIMIT $limit;",
        MAX_REVIEW_LOGS,
        memories=cast(Value, [row["id"] for row in memory]),
    )
    return BundleSource(
        records=[records[rid] for rid in sorted(records, key=str)],
        edges=u.snap.kept_edges(selected),
        projects=projects,
        includes=[m for rows in by_project.values() for m in _memberships(rows)],
        overrides=[row for row in overrides if _override_target(row) in records],
        notes=[row for row in notes if row["target"] in known],
        media=[row for row in media if row["target"] in records],
        memory=memory,
        review_log=logs,
        user=accounts[0],
    )


async def _media(u: _UserSnapshot, media: list[Row], records: list[RecordID]) -> list[Row]:
    """The owner's media plus shared media of exported rows and audio their lexemes use."""
    shared = await u.rows(
        "SELECT * FROM media WHERE owner = NONE AND target IN $targets LIMIT $limit;",
        MAX_ATTACHED,
        targets=cast(Value, records),
    )
    found = {row["id"]: row for row in [*media, *shared]}
    audio = [
        pron["audio"]
        for rid in records
        if rid.table_name == "lexeme"
        for pron in u.snap.records[rid].get("pron") or []
        if isinstance(pron.get("audio"), RecordID) and pron["audio"] not in found
    ]
    if audio:
        extra = await u.snap.rows(
            "SELECT * FROM $media " + _VISIBLE, {"media": cast(Value, list(dict.fromkeys(audio)))}
        )
        found |= {row["id"]: row for row in extra}
    if len(found) > MAX_ATTACHED:
        raise _too_large()
    return sorted(found.values(), key=lambda row: str(row["id"]))


async def load_user(db: AsyncSurrealConnection, owner: str) -> BundleSource:
    """Read everything the owner has in one transaction (media rows keep ``path`` for hashing)."""

    async def operation(txn: UUID) -> BundleSource:
        return await _load(db, RecordID("user", user_key(owner)), txn)

    return await _atomic(db, operation)
