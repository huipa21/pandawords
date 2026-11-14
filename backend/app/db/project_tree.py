"""Project selections and independent ancestor visibility, in one owner-safe snapshot."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.db.dictionary import _record
from app.domain.identity import user_key
from app.domain.project_tree import (
    ProjectMembershipRead,
    ProjectTreeLemmaRead,
    ProjectTreeLexemeRead,
    ProjectTreePage,
    ProjectTreeSenseRead,
)

# Reject oversized snapshots, never silently truncate a selection or ancestry.
MAX_MEMBERSHIPS = 10_000
MAX_PAGE_NODES = 2_000


def _too_large() -> AppError:
    return AppError("project.tree_too_large", 413, "Project tree exceeds the result bounds.")


async def _memberships(
    db: AsyncSurrealConnection, user: RecordID, project: RecordID, txn: UUID
) -> list[dict[str, Any]]:
    parameters: dict[str, Value] = {"user": user, "project": project}
    if not await _rows(db, "SELECT id FROM $project WHERE owner = $user;", parameters, txn_id=txn):
        raise AppError("project.not_found", 404, "Project not found.")
    rows = await _rows(
        db,
        "SELECT * FROM includes WHERE owner = $user AND in = $project "
        "AND in.owner = $user AND (out.owner = NONE OR out.owner = $user) LIMIT $limit;",
        {**parameters, "limit": MAX_MEMBERSHIPS + 1},
        txn_id=txn,
    )
    if len(rows) > MAX_MEMBERSHIPS:
        raise _too_large()
    return rows


def _hidden(rows: list[dict[str, Any]]) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for row in rows:
        key = encode_rid(row["out"], row["out"].table_name)
        # A retained legacy hidden edge wins until visibility updates all matching edges.
        flags[key] = flags.get(key, False) or row["hidden"]
    return flags


async def _children(
    db: AsyncSurrealConnection,
    user: RecordID,
    parent: RecordID,
    table: str,
    targets: list[RecordID] | None,
    txn: UUID,
) -> list[dict[str, Any]]:
    rows = await _rows(
        db,
        "SELECT * FROM type::table($table) WHERE in = $parent "
        "AND (owner = NONE OR owner = $user) "
        "AND (in.owner = NONE OR in.owner = $user) "
        "AND (out.owner = NONE OR out.owner = $user) "
        "AND ($targets = NONE OR out IN $targets) LIMIT $limit;",
        {
            "table": table,
            "parent": parent,
            "user": user,
            "targets": cast(Value, targets),
            "limit": MAX_PAGE_NODES + 1,
        },
        txn_id=txn,
    )
    if len(rows) > MAX_PAGE_NODES:
        raise _too_large()
    return rows


async def _tree(
    db: AsyncSurrealConnection,
    user: RecordID,
    memberships: list[dict[str, Any]],
    page: int,
    page_size: int,
    include_hidden: bool,
    txn: UUID,
) -> ProjectTreePage:
    flags = _hidden(memberships)
    lemmas = {
        encode_rid(row["out"], "lemma"): row["out"]
        for row in memberships
        if row["out"].table_name == "lemma"
        and (include_hidden or not flags[encode_rid(row["out"], "lemma")])
    }
    selected = list({row["out"] for row in memberships if row["out"].table_name == "sense"})
    items: list[ProjectTreeLemmaRead] = []
    visited = 0
    for key in sorted(lemmas)[(page - 1) * page_size : page * page_size]:
        lemma_id = lemmas[key]
        lemma = await _record(db, user, lemma_id, txn)
        if lemma is None:
            continue
        lexemes: dict[str, ProjectTreeLexemeRead] = {}
        for edge in await _children(db, user, lemma_id, "has_lexeme", None, txn):
            lexeme_id = edge["out"]
            lexeme_key = encode_rid(lexeme_id, "lexeme")
            hidden = flags.get(lexeme_key, False)
            effective = flags[key] or hidden
            if lexeme_key in lexemes or (effective and not include_hidden):
                continue
            senses: dict[str, ProjectTreeSenseRead] = {}
            for sense_edge in await _children(db, user, lexeme_id, "has_sense", selected, txn):
                sense_key = encode_rid(sense_edge["out"], "sense")
                sense_hidden = flags[sense_key]
                if sense_key in senses or ((effective or sense_hidden) and not include_hidden):
                    continue
                sense = await _record(db, user, sense_edge["out"], txn)
                if sense is not None:
                    senses[sense.id] = ProjectTreeSenseRead(
                        sense=sense, hidden=sense_hidden, effective_hidden=effective or sense_hidden
                    )
            if not senses:
                continue
            lexeme = await _record(db, user, lexeme_id, txn)
            if lexeme is not None:
                lexemes[lexeme.id] = ProjectTreeLexemeRead(
                    lexeme=lexeme,
                    hidden=hidden,
                    effective_hidden=effective,
                    senses=sorted(
                        senses.values(),
                        key=lambda node: (cast(int, node.sense.fields["rank"]), node.sense.id),
                    ),
                )
                visited += 1 + len(senses)
                if visited + len(items) + 1 > MAX_PAGE_NODES:
                    raise _too_large()
        items.append(
            ProjectTreeLemmaRead(
                lemma=lemma,
                hidden=flags[key],
                effective_hidden=flags[key],
                lexemes=sorted(lexemes.values(), key=lambda node: node.lexeme.id),
            )
        )
    return ProjectTreePage(items=items, total=len(lemmas), page=page, page_size=page_size)


async def read_tree(
    db: AsyncSurrealConnection,
    owner: str,
    project: RecordID,
    page: int,
    page_size: int,
    include_hidden: bool,
) -> ProjectTreePage:
    async def operation(txn: UUID) -> ProjectTreePage:
        user = RecordID("user", user_key(owner))
        memberships = await _memberships(db, user, project, txn)
        return await _tree(db, user, memberships, page, page_size, include_hidden, txn)

    return await _atomic(db, operation)


async def set_visibility(
    db: AsyncSurrealConnection, owner: str, project: RecordID, target: RecordID, hidden: bool
) -> ProjectMembershipRead:
    async def operation(txn: UUID) -> ProjectMembershipRead:
        user = RecordID("user", user_key(owner))
        memberships = await _memberships(db, user, project, txn)
        matching = [row for row in memberships if row["out"] == target]
        if target.table_name == "lexeme":
            # Group markers do not select senses. Require a path from an included lemma
            # to an explicitly included sense, even when any ancestor/sense is hidden.
            found = False
            senses = [row["out"] for row in memberships if row["out"].table_name == "sense"]
            for row in memberships:
                if row["out"].table_name != "lemma":
                    continue
                edges = await _children(db, user, row["out"], "has_lexeme", [target], txn)
                if edges and await _children(db, user, target, "has_sense", senses, txn):
                    found = True
                    break
            if not found:
                raise AppError("project.item_not_found", 404, "Project item not found.")
        elif not matching or await _record(db, user, target, txn) is None:
            raise AppError("project.item_not_found", 404, "Project item not found.")
        parameters: dict[str, Value] = {
            "user": user,
            "project": project,
            "target": target,
            "hidden": hidden,
        }
        if matching:
            rows = await _rows(
                db,
                "UPDATE includes SET hidden = $hidden WHERE owner = $user "
                "AND in = $project AND out = $target RETURN AFTER;",
                parameters,
                txn_id=txn,
            )
            row = sorted(rows, key=lambda item: encode_rid(item["id"], "includes"))[0]
        else:
            marker = RecordID("includes", [project, target])
            if await _rows(
                db,
                "SELECT id FROM $marker WHERE owner != $user;",
                {"marker": marker, "user": user},
                txn_id=txn,
            ):
                raise AppError(
                    "project.membership_conflict", 409, "Conflicting project membership."
                )
            rows = await _rows(
                db,
                "RELATE $project->$edge->$target CONTENT $content RETURN AFTER;",
                {
                    **parameters,
                    "edge": marker,
                    "content": {"owner": user, "hidden": hidden, "added_at": datetime.now(UTC)},
                },
                txn_id=txn,
            )
            row = rows[0]
        return ProjectMembershipRead(
            id=encode_rid(row["id"], "includes"),
            target_id=encode_rid(target, target.table_name),
            hidden=row["hidden"],
            added_at=row["added_at"],
        )

    return await _atomic(db, operation)
