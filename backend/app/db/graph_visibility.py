"""Bounded project-union authorization, including per-project hidden ancestry."""

from typing import Any, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.db.auth import _rows
from app.db.dictionary import TABLE_FIELDS

MAX_AUTH_ROWS = 10_000
MAX_EDGE_ROWS = 10_000


def too_large() -> AppError:
    return AppError(
        "graph.too_large",
        413,
        "Graph exceeds the safety bounds (maximum 300 nodes). "
        "Reduce depth or narrow node/relation filters; hide unused project selections.",
    )


async def bounded_rows(
    db: AsyncSurrealConnection,
    query: str,
    parameters: dict[str, Value],
    txn: UUID,
    limit: int,
) -> list[dict[str, Any]]:
    rows = await _rows(db, query, {**parameters, "limit": limit + 1}, txn_id=txn)
    if len(rows) > limit:
        raise too_large()
    return rows


async def visible(
    db: AsyncSurrealConnection, user: RecordID, txn: UUID, project: RecordID | None = None
) -> set[RecordID]:
    if project is not None and not await _rows(
        db,
        "SELECT id FROM $project WHERE owner = $user;",
        {"project": project, "user": user},
        txn_id=txn,
    ):
        raise AppError("project.not_found", 404, "Project not found.")
    memberships = await bounded_rows(
        db,
        "SELECT in, out, hidden FROM includes WHERE owner = $user AND in.owner = $user "
        "AND (out.owner = NONE OR out.owner = $user) "
        "AND ($project = NONE OR in = $project) LIMIT $limit;",
        {"user": user, "project": project},
        txn,
        MAX_AUTH_ROWS,
    )
    targets = {row["out"] for row in memberships}
    parents: dict[RecordID, set[RecordID]] = {}
    # Read sense parents first so a hidden lemma also hides its selected grandchildren,
    # even when the intermediate lexeme has no includes marker.
    for relation in ("has_sense", "has_lexeme"):
        edges = await bounded_rows(
            db,
            "SELECT in, out FROM type::table($table) WHERE out IN $targets "
            "AND (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) LIMIT $limit;",
            {"table": relation, "targets": cast(Value, list(targets)), "user": user},
            txn,
            MAX_EDGE_ROWS,
        )
        for edge in edges:
            parents.setdefault(edge["out"], set()).add(edge["in"])
            targets.add(edge["in"])
    hidden: dict[RecordID, set[RecordID]] = {}
    for row in memberships:
        if row["hidden"]:
            hidden.setdefault(row["in"], set()).add(row["out"])
    authorized: set[RecordID] = set()
    for row in memberships:
        blocked = hidden.get(row["in"], set())
        target = row["out"]
        ancestors = parents.get(target, set())
        grandparents = {parent for ancestor in ancestors for parent in parents.get(ancestor, set())}
        if not ({target} | ancestors | grandparents) & blocked:
            authorized.add(target)
    for table in () if project is not None else TABLE_FIELDS:
        owned = await bounded_rows(
            db,
            "SELECT id FROM type::table($table) WHERE owner = $user LIMIT $limit;",
            {"table": table, "user": user},
            txn,
            MAX_AUTH_ROWS,
        )
        authorized.update(row["id"] for row in owned)
    return authorized
