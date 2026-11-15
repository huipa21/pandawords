"""Explicit, rate-limited worker optimization, independent of review confirmation."""

import asyncio
import json
import sys
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from surrealdb import AsyncSurrealConnection

from app.db import srs_optimization as repository
from app.domain.jobs import JobCreate
from app.domain.srs import fingerprint
from app.domain.srs_optimization import (
    MIN_CARDS,
    MIN_NEW_TRANSITIONS,
    MIN_TRANSITIONS,
    OPTIMIZER_TIMEOUT_SECONDS,
    OPTIMIZER_VERSION,
    OptimizationRead,
    validated_parameters,
)
from app.services import jobs
from app.services.srs_optimization_history import eligible_transitions, training_history


async def read(db: AsyncSurrealConnection, owner: str) -> OptimizationRead:
    row = await repository.state(db, owner)
    return OptimizationRead.model_validate(row["result"]) if row else OptimizationRead()


async def request(db: AsyncSurrealConnection, owner: str) -> None:
    now = datetime.now(UTC)
    await jobs.enqueue(
        db,
        JobCreate(type="srs_optimize", owner=owner),
        dedup_key=f"srs_optimize:{now.date().isoformat()}",
    )


async def compute(logs: list[dict[str, Any]]) -> tuple[str, object]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.worker.fsrs_optimizer",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(json.dumps(logs).encode()), timeout=OPTIMIZER_TIMEOUT_SECONDS
        )
        if process.returncode != 0:
            return "failed", None
        result = json.loads(stdout)
        if not isinstance(result, dict) or result.get("status") not in {
            "success",
            "unavailable",
            "failed",
        }:
            return "failed", None
        return result["status"], result.get("parameters")
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()


async def optimize(
    db: AsyncSurrealConnection, owner: str, *, now: datetime | None = None
) -> OptimizationRead:
    now = now or datetime.now(UTC)
    if now.utcoffset() is None:
        raise ValueError("Optimization time must be timezone aware")
    now = now.astimezone(UTC)
    run_id = await repository.claim(db, owner, now)
    if run_id is None:
        return await read(db, owner)
    result = OptimizationRead(status="failed", reason="optimizer_error", at=now)
    values = None
    try:
        rows = await repository.history(db, owner)
        logs, excluded = training_history(rows, owner, now)
        count, cards = eligible_transitions(logs)
        digest = fingerprint(logs)
        result.eligible_reviews = count
        result.excluded_reviews = excluded
        result.history_fingerprint = digest
        previous = await repository.state(db, owner)
        if count < MIN_TRANSITIONS or cards < MIN_CARDS:
            result.status, result.reason = "insufficient_history", "minimum_history"
        else:
            try:
                previous_valid = previous.get("parameters_version") == OPTIMIZER_VERSION and bool(
                    validated_parameters(previous.get("parameters"))
                )
            except ValueError:
                previous_valid = False
            since = previous.get("optimized_at") if previous_valid else None
            new_count, _ = eligible_transitions(logs, since=since)
            if since is not None and new_count < MIN_NEW_TRANSITIONS:
                result.status, result.reason = "insufficient_history", "minimum_new_history"
            else:
                status, output = await compute(logs)
                if status == "unavailable":
                    result.status, result.reason = "unavailable", "optimizer_not_installed"
                elif status == "success":
                    values = validated_parameters(output)
                    result.status, result.reason = "success", None
    except asyncio.CancelledError:
        result.status, result.reason = "failed", "cancelled"
        await repository.finish(db, owner, run_id, result)
        raise
    except Exception:
        # Public statuses contain no provider exception, log data or filesystem paths.
        result.status, result.reason = "failed", "optimizer_error"
    await repository.finish(db, owner, run_id, result, values)
    return await read(db, owner)
