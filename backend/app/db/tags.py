"""Owner-scoped tags and independently checked membership endpoints."""

from typing import Any, Literal
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.db.user_dictionary import require_visible
from app.domain.identity import user_key
from app.domain.tags import TagAssignmentRead, TagCreate, TagRead, TagUpdate


def _read(row: dict[str, Any]) -> TagRead:
    return TagRead(
        id=encode_rid(row["id"], "tag"),
        name=row["name"],
        kind=row["kind"],
        readonly=row.get("owner") is None,
    )


async def _lock(db: AsyncSurrealConnection, user: RecordID, txn: UUID) -> None:
    # A real write serializes opposing hierarchy edits, including phantom paths.
    await _rows(
        db,
        "UPDATE $user SET tag_revision += 1 WHERE id = $user;",
        {"user": user},
        txn_id=txn,
    )


async def create(db: AsyncSurrealConnection, owner: str, data: TagCreate) -> TagRead:
    rows = await _rows(
        db,
        "CREATE $tag CONTENT $content;",
        {
            "tag": RecordID("tag", uuid4().hex),
            "content": {**data.model_dump(), "owner": RecordID("user", user_key(owner))},
        },
    )
    return _read(rows[0])


async def list_tags(db: AsyncSurrealConnection, owner: str) -> list[TagRead]:
    rows = await _rows(
        db,
        "SELECT * FROM tag WHERE owner = NONE OR owner = $user ORDER BY name, id;",
        {"user": RecordID("user", user_key(owner))},
    )
    return [_read(row) for row in rows]


async def manage(
    db: AsyncSurrealConnection,
    owner: str,
    tag: RecordID,
    action: Literal["get", "patch", "delete"],
    data: TagUpdate | None = None,
) -> TagRead | None:
    async def operation(txn: UUID) -> TagRead | None:
        user = RecordID("user", user_key(owner))
        if action != "get":
            await _lock(db, user, txn)
        row = await require_visible(db, user, tag, txn)
        if action != "get" and row.get("owner") != user:
            raise AppError("tag.readonly", 403, "Shared tags are read-only.")
        params: dict[str, Value] = {"tag": tag, "user": user}
        if action == "delete":
            foreign = await _rows(
                db,
                "SELECT id FROM member_of WHERE (in = $tag OR out = $tag) "
                "AND (owner = NONE OR owner != $user) LIMIT 1;",
                params,
                txn_id=txn,
            )
            # SurrealDB cascades all incident relations when an endpoint is deleted.
            if foreign:
                raise AppError("tag.in_use", 409, "Tag has protected memberships.")
            await _rows(
                db,
                "DELETE member_of WHERE owner = $user AND (in = $tag OR out = $tag);",
                params,
                txn_id=txn,
            )
            await _rows(db, "DELETE $tag WHERE owner = $user;", params, txn_id=txn)
            return None
        if data is not None:
            rows = await _rows(
                db,
                "UPDATE $tag MERGE $changes WHERE owner = $user RETURN AFTER;",
                {**params, "changes": data.model_dump(exclude_unset=True)},
                txn_id=txn,
            )
            row = rows[0]
        return _read(row)

    return await _atomic(db, operation)


async def memberships(
    db: AsyncSurrealConnection,
    owner: str,
    target: RecordID,
) -> list[TagAssignmentRead]:
    async def operation(txn: UUID) -> list[TagAssignmentRead]:
        user = RecordID("user", user_key(owner))
        await require_visible(db, user, target, txn)
        rows = await _rows(
            db,
            "SELECT *, out.* AS tag FROM member_of WHERE in = $target "
            "AND (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) ORDER BY id;",
            {"target": target, "user": user},
            txn_id=txn,
        )
        return [
            TagAssignmentRead(tag=_read(row["tag"]), readonly=row.get("owner") != user)
            for row in rows
            if isinstance(row.get("tag"), dict) and "name" in row["tag"]
        ]

    return await _atomic(db, operation)


async def assign(
    db: AsyncSurrealConnection,
    owner: str,
    tag: RecordID,
    target: RecordID,
    *,
    remove: bool,
) -> None:
    async def operation(txn: UUID) -> None:
        user = RecordID("user", user_key(owner))
        await _lock(db, user, txn)
        await require_visible(db, user, target, txn)
        await require_visible(db, user, tag, txn)
        params: dict[str, Value] = {"tag": tag, "target": target, "user": user}
        if remove:
            await _rows(
                db,
                "DELETE member_of WHERE owner = $user AND in = $target AND out = $tag;",
                params,
                txn_id=txn,
            )
            return
        if target.table_name == "tag":
            edges = await _rows(
                db,
                "SELECT in, out FROM member_of WHERE "
                "(owner = NONE OR owner = $user) AND "
                "(in.owner = NONE OR in.owner = $user) AND "
                "(out.owner = NONE OR out.owner = $user);",
                {"user": user},
                txn_id=txn,
            )
            pending, visited = [tag], set()
            while pending:
                node = pending.pop()
                if node == target:
                    raise AppError("tag.cycle", 409, "Tag hierarchy cannot contain cycles.")
                key = str(node)
                if key not in visited:
                    visited.add(key)
                    pending.extend(edge["out"] for edge in edges if edge["in"] == node)
        existing = await _rows(
            db,
            "SELECT * FROM member_of WHERE owner = $user AND in = $target AND out = $tag;",
            params,
            txn_id=txn,
        )
        if not existing:
            await _rows(
                db,
                "RELATE $target->$edge->$tag SET owner = $user;",
                {**params, "edge": RecordID("member_of", uuid4().hex)},
                txn_id=txn,
            )

    await _atomic(db, operation)
