from datetime import UTC, datetime
from typing import Any, cast

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.auth import _rows
from app.db.migration_store import checked_query
from app.db.srs import user_record
from app.domain.auth import UserPreferences
from app.domain.srs import ReviewReceipt
from app.domain.srs_optimization import MAX_CARDS, MAX_FETCHED_LOGS


async def seed(db: AsyncSurrealConnection, rows: list[dict[str, Any]]) -> None:
    memories: dict[str, tuple[RecordID, dict[str, Any], ReviewReceipt]] = {}
    for row in rows:
        receipt = ReviewReceipt.model_validate(row["receipt"])
        memory: RecordID = row["memory"]
        previous = memories.get(receipt.memory.id)
        if previous is None or receipt.at > previous[2].at:
            memories[receipt.memory.id] = (memory, row, receipt)
    for memory, row, receipt in memories.values():
        parts = memory.id
        assert isinstance(parts, list) and len(parts) == 2
        await _rows(
            db,
            "UPSERT $id CONTENT $data WHERE owner = NONE OR owner = $user;",
            {
                "id": memory,
                "user": row["owner"],
                "data": cast(
                    Value,
                    {
                        "owner": row["owner"],
                        "sense": parts[1],
                        "introduced": True,
                        **receipt.memory.card.model_dump(),
                    },
                ),
            },
        )
    for start in range(0, len(rows), 128):
        await _rows(
            db,
            "INSERT INTO review_log $data;",
            {"data": cast(Value, rows[start : start + 128])},
        )


async def replace_parameters(
    db: AsyncSurrealConnection, owner: str, values: list[float], version: str
) -> None:
    await _rows(
        db,
        "UPDATE srs_optimization SET parameters = $values, parameters_version = $version "
        "WHERE owner = $user;",
        {"user": user_record(owner), "values": cast(Value, values), "version": version},
    )


async def set_preferences(db: AsyncSurrealConnection, owner: str, prefs: UserPreferences) -> None:
    await _rows(
        db,
        "UPDATE $user SET prefs = $prefs WHERE id = $user;",
        {"user": user_record(owner), "prefs": cast(Value, prefs.model_dump())},
    )


async def insert_foreign_identity(
    db: AsyncWsSurrealConnection, owner: str, identity_owner: str
) -> None:
    await checked_query(
        db,
        "CREATE $id SET owner = $user, run_id = $run, attempted_at = $now, result = $result;",
        {
            "id": RecordID("srs_optimization", [user_record(identity_owner)]),
            "user": user_record(owner),
            "run": "bad-identity",
            "now": datetime.now(UTC),
            "result": {"status": "not_run"},
        },
    )


async def history_plans(
    db: AsyncWsSurrealConnection, owner: str, memory: RecordID
) -> tuple[Any, Any]:
    user = user_record(owner)
    cards = await db.query(
        "SELECT id, last_review FROM memory WHERE owner = $user AND introduced = true "
        "AND last_review != NONE ORDER BY last_review DESC, id DESC LIMIT $limit EXPLAIN FULL;",
        {"user": user, "limit": MAX_CARDS},
    ).first()
    reviews = await db.query(
        "SELECT * FROM (SELECT * FROM review_log WITH INDEX review_log_owner_at "
        "WHERE owner = $user ORDER BY at DESC, id DESC LIMIT $limit) "
        "WHERE owner = $user AND memory IN $memories AND memory.owner = $user "
        "ORDER BY at DESC, id DESC EXPLAIN FULL;",
        {"user": user, "memories": [memory], "limit": MAX_FETCHED_LOGS},
    ).first()
    return cards, reviews
