"""Bounded composition lookup; endpoints and each relation have independent ACLs."""

from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.domain.identity import user_key


async def containing_phrases(
    db: AsyncSurrealConnection, owner: str, target: RecordID, *, offset: int, limit: int
) -> list[str]:
    async def operation(txn: UUID) -> list[str]:
        params: dict[str, Value] = {"user": RecordID("user", user_key(owner)), "target": target}
        targets: list[Value] = [target]
        if target.table_name == "lemma":
            rows = await _rows(
                db,
                "SELECT out FROM has_lexeme WHERE in = $target "
                "AND (owner = NONE OR owner = $user) "
                "AND (in.owner = NONE OR in.owner = $user) "
                "AND (out.owner = NONE OR out.owner = $user);",
                params,
                txn_id=txn,
            )
            targets = [row["out"] for row in rows]
        rows = await _rows(
            db,
            "SELECT id, text FROM lemma WHERE kind = 'phrase' "
            "AND (owner = NONE OR owner = $user) "
            "AND id IN array::flatten((SELECT VALUE <-(contains WHERE "
            "(owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user)).in FROM $targets "
            "WHERE owner = NONE OR owner = $user)) "
            "ORDER BY text ASC, id ASC LIMIT $limit START $offset;",
            {**params, "targets": targets, "limit": limit, "offset": offset},
            txn_id=txn,
        )
        return [encode_rid(row["id"], "lemma") for row in rows]

    return await _atomic(db, operation)
