"""Bounded offline prefetch: explicit fixed leases over the normal attempt contract."""

from datetime import timedelta
from uuid import UUID

from surrealdb import AsyncSurrealConnection

from app.core.errors import AppError
from app.db import exercises as repository
from app.db.auth import _atomic
from app.domain.exercises import (
    Attempt,
    AttemptCreate,
    AttemptOpen,
    OfflineBatchRead,
    OfflinePrefetch,
)
from app.services import exercise_attempts, study_plan
from app.services.exercise_registry import ExerciseRegistry, registry

OFFLINE_ATTEMPT_TTL = timedelta(hours=24)
OFFLINE_ACTIVE_LIMIT = 20


async def prefetch(
    db: AsyncSurrealConnection,
    owner: str,
    data: OfflinePrefetch,
    *,
    plugins: ExerciseRegistry = registry,
) -> OfflineBatchRead:
    """Return held offline attempts first, then issue new ones up to both bounds.

    Held leases are returned unchanged (same id and expiry), including their final
    minutes. A transactional owner guard bounds issuance across concurrent requests.
    """
    plan = await study_plan.read_plan(db, owner, data.project_id, limit=OFFLINE_ACTIVE_LIMIT * 2)
    cutoff = exercise_attempts._now()

    async def operation(txn: UUID) -> list[Attempt]:
        return await repository.open_leases_after(db, owner, cutoff, txn)

    held = await _atomic(db, operation)
    versions = {item.memory.sense_id: item.memory_version for item in plan.queue}
    current = [
        attempt
        for attempt in held
        if attempt.status == "open"
        and attempt.project_id == data.project_id
        and versions.get(attempt.sense_id) == attempt.expected_version
    ]
    positions = {item.memory.sense_id: index for index, item in enumerate(plan.queue)}
    current.sort(key=lambda attempt: (positions[attempt.sense_id], attempt.id))
    attempts = [exercise_attempts.public(attempt) for attempt in current[: data.limit]]
    capacity = min(data.limit - len(attempts), OFFLINE_ACTIVE_LIMIT - len(held))
    # Stale held leases stay counted against the bound but no longer block their sense.
    taken = {attempt.sense_id for attempt in current}
    for item in plan.queue:
        if capacity <= 0:
            break
        if item.memory.sense_id in taken:
            continue
        try:
            issued = await exercise_attempts.create_attempt(
                db,
                owner,
                AttemptCreate(project_id=data.project_id, sense_id=item.memory.sense_id),
                plugins=plugins,
                ttl=OFFLINE_ATTEMPT_TTL,
                offline_limit=OFFLINE_ACTIVE_LIMIT,
            )
        except AppError as error:
            if error.code == "exercise.offline_limit":
                break
            if error.code != "exercise.no_usable":
                raise
            continue
        attempts.append(issued)
        capacity -= 1
    return OfflineBatchRead(
        project_id=data.project_id,
        attempts=tuple(a for a in attempts if isinstance(a, AttemptOpen)),
        lease_seconds=int(OFFLINE_ATTEMPT_TTL.total_seconds()),
        active_limit=OFFLINE_ACTIVE_LIMIT,
    )
