"""Persistent cache and atomic attempt reservations, with explicit owner predicates."""

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID

from app.db.auth import _atomic, _rows
from app.domain.identity import user_key


def owner_record(user: str) -> RecordID:
    return RecordID("user", user_key(user))


def _cache_record(key: str, owner: RecordID | None) -> RecordID:
    identity = hashlib.sha256(f"{owner}:{key}".encode()).hexdigest()
    return RecordID("llm_cache", identity)


async def read_cache(db: AsyncSurrealConnection, key: str, owner: RecordID | None) -> str | None:
    rows = await _rows(
        db,
        "SELECT response_json FROM $id WHERE owner = $owner AND key = $key;",
        {"id": _cache_record(key, owner), "owner": owner, "key": key},
    )
    return rows[0]["response_json"] if rows else None


async def write_cache(
    db: AsyncSurrealConnection, key: str, owner: RecordID | None, response_json: str
) -> None:
    async def operation(txn: UUID) -> None:
        rows = await _rows(
            db,
            "SELECT id FROM $id WHERE owner = $owner AND key = $key;",
            {"id": _cache_record(key, owner), "owner": owner, "key": key},
            txn_id=txn,
        )
        if not rows:
            await _rows(
                db,
                "CREATE $id CONTENT $data;",
                {
                    "id": _cache_record(key, owner),
                    "data": {
                        "owner": owner,
                        "key": key,
                        "response_json": response_json,
                    },
                },
                txn_id=txn,
            )

    await _atomic(db, operation)


async def reserve_attempt(
    db: AsyncSurrealConnection, user: str, limit: int, *, now: datetime | None = None
) -> bool:
    if limit <= 0:
        return False
    day = (now or datetime.now(UTC)).astimezone(UTC).date().isoformat()
    owner = owner_record(user)
    record = RecordID("llm_budget", [owner, day])

    async def operation(txn: UUID) -> bool:
        rows = await _rows(
            db,
            "SELECT attempts FROM $id WHERE owner = $owner AND day = $day;",
            {"id": record, "owner": owner, "day": day},
            txn_id=txn,
        )
        if rows:
            updated = await _rows(
                db,
                "UPDATE $id SET attempts += 1 "
                "WHERE owner = $owner AND day = $day AND attempts < $limit RETURN AFTER;",
                {"id": record, "owner": owner, "day": day, "limit": limit},
                txn_id=txn,
            )
            return bool(updated)
        await _rows(
            db,
            "CREATE $id CONTENT $data;",
            {"id": record, "data": {"owner": owner, "day": day, "attempts": 1}},
            txn_id=txn,
        )
        return True

    return await _atomic(db, operation)


async def shared_inputs(
    db: AsyncSurrealConnection, sources: tuple[RecordID, ...]
) -> dict[str, Any]:
    """Never accept arbitrary user text or effective owner overlays into a shared key."""
    content: list[dict[str, Any]] = []
    for source in sources:
        if source.table_name not in {"lemma", "lexeme", "sense"}:
            raise ValueError("Unsupported shared source")
        rows = await _rows(
            db,
            "SELECT * FROM $id WHERE owner = NONE;",
            {"id": source},
        )
        if not rows:
            raise ValueError("Shared source unavailable")
        fields = {
            "lemma": ("text", "lang", "kind"),
            "lexeme": ("pos", "forms"),
            "sense": ("definition", "gloss", "examples"),
        }[source.table_name]
        content.append({"id": str(source), **{key: rows[0][key] for key in fields}})
    return {"sources": content}
