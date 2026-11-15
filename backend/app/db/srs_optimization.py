"""Owner-scoped optimization state; never updates cards, preferences or review logs."""

from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.db.auth import _atomic, _rows
from app.db.srs import user_record
from app.domain.srs_optimization import (
    MAX_CARDS,
    MAX_FETCHED_LOGS,
    MAX_REVIEWS_PER_CARD,
    OPTIMIZER_VERSION,
    OptimizationRead,
    validated_parameters,
)


async def state(db: AsyncSurrealConnection, owner: str, txn: UUID | None = None) -> dict[str, Any]:
    rows = await _rows(
        db,
        "SELECT * FROM srs_optimization WHERE owner = $user;",
        {"user": user_record(owner)},
        txn_id=txn,
    )
    return rows[0] if rows else {}


async def parameters(db: AsyncSurrealConnection, owner: str, txn: UUID) -> list[float] | None:
    row = await state(db, owner, txn)
    if row.get("parameters_version") != OPTIMIZER_VERSION:
        return None
    try:
        return validated_parameters(row.get("parameters"))
    except ValueError:
        return None


async def claim(db: AsyncSurrealConnection, owner: str, now: datetime) -> str | None:
    async def operation(txn: UUID) -> str | None:
        row = await state(db, owner, txn)
        if row:
            status = row["result"]["status"]
            if status == "running" and now - row["attempted_at"] < timedelta(minutes=10):
                return None
            if status not in {"running", "success"} and now - row["attempted_at"] < timedelta(
                days=1
            ):
                return None
            try:
                valid_current = row.get("parameters_version") == OPTIMIZER_VERSION and bool(
                    validated_parameters(row.get("parameters"))
                )
            except ValueError:
                valid_current = False
            if (
                valid_current
                and row.get("optimized_at")
                and now - row["optimized_at"] < timedelta(days=30)
            ):
                return None
        run_id = uuid4().hex
        claimed = await _rows(
            db,
            "UPSERT $id SET owner = $user, run_id = $run, attempted_at = $now, "
            "result = $result WHERE owner = NONE OR owner = $user RETURN AFTER;",
            {
                "id": RecordID("srs_optimization", [user_record(owner)]),
                "user": user_record(owner),
                "run": run_id,
                "now": now,
                "result": cast(Value, OptimizationRead(status="running", at=now).model_dump()),
            },
            txn_id=txn,
        )
        if not claimed:
            raise ValueError("Optimization identity conflict")
        return run_id

    return await _atomic(db, operation)


async def history(db: AsyncSurrealConnection, owner: str) -> list[dict[str, Any]]:
    user = user_record(owner)
    cards = await _rows(
        db,
        "SELECT id, last_review FROM memory WHERE owner = $user AND introduced = true "
        "AND last_review != NONE ORDER BY last_review DESC, id DESC LIMIT $limit;",
        {"user": user, "limit": MAX_CARDS},
    )
    if not cards:
        return []
    rows = await _rows(
        db,
        "SELECT * FROM (SELECT * FROM review_log WITH INDEX review_log_owner_at "
        "WHERE owner = $user ORDER BY at DESC, id DESC LIMIT $limit) "
        "WHERE owner = $user AND memory IN $memories AND memory.owner = $user "
        "ORDER BY at DESC, id DESC;",
        {
            "user": user,
            "memories": cast(Value, [card["id"] for card in cards]),
            "limit": MAX_FETCHED_LOGS,
        },
    )
    counts: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    for row in rows:
        memory = str(row["memory"])
        counts[memory] = counts.get(memory, 0) + 1
        if counts[memory] <= MAX_REVIEWS_PER_CARD + 1:
            selected.append(row)
    return selected


async def finish(
    db: AsyncSurrealConnection,
    owner: str,
    run_id: str,
    result: OptimizationRead,
    values: list[float] | None = None,
) -> bool:
    data: dict[str, Value] = {
        "user": user_record(owner),
        "run": run_id,
        "result": cast(Value, result.model_dump()),
    }
    if values is not None:
        if result.status != "success" or result.at is None or result.history_fingerprint is None:
            raise ValueError("Successful optimization metadata is required")
        data.update(
            parameters=cast(Value, validated_parameters(values)),
            version=OPTIMIZER_VERSION,
            now=result.at,
            count=result.eligible_reviews,
            fingerprint=result.history_fingerprint,
        )
        rows = await _rows(
            db,
            "UPDATE srs_optimization SET result = $result, parameters = $parameters, "
            "parameters_version = $version, optimized_at = $now, trained_reviews = $count, "
            "parameters_fingerprint = $fingerprint "
            "WHERE owner = $user AND run_id = $run AND result.status = 'running' RETURN AFTER;",
            data,
        )
    else:
        rows = await _rows(
            db,
            "UPDATE srs_optimization SET result = $result "
            "WHERE owner = $user AND run_id = $run AND result.status = 'running' RETURN AFTER;",
            data,
        )
    return bool(rows)
