"""Owner-scoped planning snapshots and persisted membership ordering."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _rows
from app.db.project_tree import _children, _hidden, _memberships
from app.db.projects import _read
from app.db.srs import memory_read, user_record
from app.domain.projects import ProjectRead
from app.domain.srs import MemoryRead

MAX_PROJECTS = 1_000
MAX_HISTORY = 100_000


@dataclass
class ProjectSnapshot:
    project: ProjectRead
    cards: list[MemoryRead]


def membership_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        (row for row in rows if row["out"].table_name == "sense"),
        key=lambda row: (
            row.get("study_order") is None,
            row.get("study_order") or 0,
            row["added_at"],
            encode_rid(row["id"], "includes"),
        ),
    )
    seen: set[RecordID] = set()
    unique = []
    for row in ordered:
        if row["out"] not in seen:
            seen.add(row["out"])
            unique.append(row)
    return unique


async def visible_senses(
    db: AsyncSurrealConnection, user: RecordID, rows: list[dict[str, Any]], txn: UUID
) -> set[RecordID]:
    flags = _hidden(rows)
    selected = [row["out"] for row in membership_order(rows)]
    visible: set[RecordID] = set()
    for row in rows:
        lemma = row["out"]
        if lemma.table_name != "lemma" or flags[encode_rid(lemma, "lemma")]:
            continue
        for edge in await _children(db, user, lemma, "has_lexeme", None, txn):
            lexeme = edge["out"]
            if flags.get(encode_rid(lexeme, "lexeme"), False):
                continue
            for sense_edge in await _children(db, user, lexeme, "has_sense", selected, txn):
                sense = sense_edge["out"]
                if not flags[encode_rid(sense, "sense")]:
                    visible.add(sense)
    return visible


async def snapshot(
    db: AsyncSurrealConnection, owner: str, project: RecordID, txn: UUID
) -> ProjectSnapshot:
    user = user_record(owner)
    rows = await _memberships(db, user, project, txn)
    visible = await visible_senses(db, user, rows, txn)
    projects = await _rows(
        db,
        "SELECT * FROM $project WHERE owner = $user;",
        {"project": project, "user": user},
        txn_id=txn,
    )
    memories = await _rows(
        db,
        "SELECT * FROM memory WHERE owner = $user AND sense IN $senses;",
        {"user": user, "senses": cast(Value, list(visible))},
        txn_id=txn,
    )
    by_sense = {row["sense"]: memory_read(row) for row in memories}
    return ProjectSnapshot(
        _read(projects[0]),
        [by_sense[row["out"]] for row in membership_order(rows) if row["out"] in by_sense],
    )


async def project_ids(db: AsyncSurrealConnection, owner: str, txn: UUID) -> list[RecordID]:
    rows = await _rows(
        db,
        "SELECT id FROM project WHERE owner = $user ORDER BY id LIMIT $limit;",
        {"user": user_record(owner), "limit": MAX_PROJECTS + 1},
        txn_id=txn,
    )
    if len(rows) > MAX_PROJECTS:
        raise AppError("study.too_large", 413, "Dashboard exceeds project bounds.")
    return [row["id"] for row in rows]


async def history(
    db: AsyncSurrealConnection, owner: str, end: datetime, txn: UUID
) -> list[dict[str, Any]]:
    rows = await _rows(
        db,
        "SELECT project, at, correct, is_introduction FROM review_log "
        "WHERE owner = $user AND at <= $end LIMIT $limit;",
        {"user": user_record(owner), "end": end, "limit": MAX_HISTORY + 1},
        txn_id=txn,
    )
    if len(rows) > MAX_HISTORY:
        raise AppError("study.too_large", 413, "Review history exceeds planning bounds.")
    return rows


async def reorder(
    db: AsyncSurrealConnection, owner: str, project: RecordID, senses: list[RecordID], txn: UUID
) -> list[str]:
    user = user_record(owner)
    rows = await _memberships(db, user, project, txn)
    visible = await visible_senses(db, user, rows, txn)
    if set(senses) != visible:
        raise AppError(
            "study.invalid_order", 409, "Supply every visible selected sense exactly once."
        )
    ordered = membership_order(rows)
    replacements = iter(senses)
    result = [next(replacements) if row["out"] in visible else row["out"] for row in ordered]
    # A real project write serializes concurrent reorder and scheduling transactions.
    await _rows(
        db,
        "UPDATE $project SET srs_revision += 1 WHERE owner = $user;",
        {"project": project, "user": user},
        txn_id=txn,
    )
    for position, sense in enumerate(result):
        await _rows(
            db,
            "UPDATE includes SET study_order = $position WHERE owner = $user "
            "AND in = $project AND in.owner = $user AND out = $sense "
            "AND (out.owner = NONE OR out.owner = $user);",
            {"user": user, "project": project, "sense": sense, "position": position},
            txn_id=txn,
        )
    return [encode_rid(sense, "sense") for sense in result]
