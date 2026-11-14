"""Bounded morphology reads: authorize relations and both endpoints independently."""

from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.db.user_dictionary import not_found, require_visible
from app.domain.identity import user_key
from app.domain.morphology import MorphemeRead, MorphGroupMemberRead


async def lexeme_morphemes(
    db: AsyncSurrealConnection, owner: str, lexeme: RecordID
) -> list[MorphemeRead]:
    if lexeme.table_name != "lexeme":
        raise not_found()

    async def operation(txn: UUID) -> list[MorphemeRead]:
        user = RecordID("user", user_key(owner))
        await require_visible(db, user, lexeme, txn)
        rows = await _rows(
            db,
            "SELECT id, order, source, owner, out.* AS morpheme FROM composed_of "
            "WHERE in = $lexeme AND (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) ORDER BY order, id LIMIT 256;",
            {"lexeme": lexeme, "user": user},
            txn_id=txn,
        )
        return [
            MorphemeRead(
                id=encode_rid(row["morpheme"]["id"], "morpheme"),
                text=row["morpheme"]["text"],
                type=row["morpheme"]["type"],
                meaning=row["morpheme"].get("meaning"),
                order=row["order"],
                source=row.get("source"),
                readonly=row.get("owner") is None,
            )
            for row in rows
        ]

    return await _atomic(db, operation)


async def group_members(
    db: AsyncSurrealConnection, owner: str, target: RecordID, *, limit: int = 100
) -> list[MorphGroupMemberRead]:
    if target.table_name not in {"sense", "morpheme"} or not 1 <= limit <= 300:
        raise not_found()

    async def operation(txn: UUID) -> list[MorphGroupMemberRead]:
        user = RecordID("user", user_key(owner))
        await require_visible(db, user, target, txn)
        groups = await _rows(
            db,
            "SELECT id, out FROM member_of WHERE in = $target "
            "AND (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) AND out.kind = 'morph_group' "
            "ORDER BY id LIMIT 256;",
            {"target": target, "user": user},
            txn_id=txn,
        )
        rows = await _rows(
            db,
            "SELECT id, in AS member FROM member_of WHERE out IN $groups AND in != $target "
            "AND (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) AND out.kind = 'morph_group' "
            "ORDER BY in, id LIMIT 4096;",
            {"groups": [row["out"] for row in groups], "target": target, "user": user},
            txn_id=txn,
        )
        members = {
            str(row["member"]): row["member"]
            for row in rows
            if row["member"].table_name in {"sense", "morpheme"}
        }
        return [
            MorphGroupMemberRead(id=encode_rid(record, record.table_name), table=record.table_name)
            for _, record in sorted(members.items())[:limit]
        ]

    return await _atomic(db, operation)
