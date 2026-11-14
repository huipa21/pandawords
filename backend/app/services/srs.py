"""FSRS scheduling boundary shared by daily plans and trusted exercise attempts."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fsrs import Rating, Scheduler
from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import srs as repository
from app.db.auth import _atomic
from app.domain.srs import (
    CardState,
    FrameworkGrade,
    GradedReview,
    MemoryRead,
    ReviewReceipt,
    SrsPreferences,
    fingerprint,
)
from app.services.srs_rating import auto_rating


def _decode(value: str, table: str) -> RecordID:
    try:
        return decode_rid(value, table)
    except ValueError:
        raise AppError("srs.not_found", 404, "Study record not found.") from None


async def ensure_card(
    db: AsyncSurrealConnection, owner: str, sense_id: str, *, txn_id: UUID
) -> bool:
    """Create only if absent, inside the caller's existing add transaction."""
    return await repository.ensure_memory(db, owner, _decode(sense_id, "sense"), txn_id)


async def reconcile_memberships(db: AsyncSurrealConnection, owner: str) -> int:
    """Backfill all selected senses, including hidden selections, without resets."""

    async def operation(txn: UUID) -> int:
        count = 0
        for sense in await repository.selected_senses(db, owner, txn):
            count += await repository.ensure_memory(db, owner, sense, txn)
        return count

    return await _atomic(db, operation)


async def read_memory(db: AsyncSurrealConnection, owner: str, sense_id: str) -> MemoryRead:
    memory = await repository.read_memory(db, owner, _decode(sense_id, "sense"))
    if memory is None:
        await reconcile_memberships(db, owner)
        memory = await repository.read_memory(db, owner, _decode(sense_id, "sense"))
        if memory is None:
            raise AppError("srs.not_found", 404, "Memory not found.")
    return memory


async def read_preferences(db: AsyncSurrealConnection, owner: str) -> SrsPreferences:
    return await repository.preferences(db, owner)


async def update_preferences(
    db: AsyncSurrealConnection, owner: str, data: SrsPreferences
) -> SrsPreferences:
    return await repository.preferences(db, owner, update=data)


async def grade_review(
    db: AsyncSurrealConnection,
    settings: Settings,
    owner: str,
    *,
    attempt_id: str,
    project_id: str,
    sense_id: str,
    expected_version: str,
    grade: FrameworkGrade,
) -> GradedReview:
    """Framework calls after server grading; persist the returned value in its attempt."""

    async def operation(txn: UUID) -> GradedReview:
        sense, project = _decode(sense_id, "sense"), _decode(project_id, "project")
        await repository.eligible_project(db, owner, project, sense, txn)
        memory = await repository.read_memory(db, owner, sense, txn)
        if memory is None:
            raise AppError("srs.not_found", 404, "Memory not found.")
        if memory.version != expected_version:
            raise AppError("srs.stale_review", 409, "Memory has already changed.")
        history = await repository.prior_correct(db, owner, grade.exercise, txn)
        return GradedReview(
            attempt_id=attempt_id,
            project_id=project_id,
            sense_id=sense_id,
            expected_version=expected_version,
            grade=grade,
            auto_rating=auto_rating(grade, history, settings),
        )

    return await _atomic(db, operation)


async def apply_review(
    db: AsyncSurrealConnection,
    owner: str,
    review: GradedReview,
    rating: Rating,
    *,
    now: datetime | None = None,
) -> ReviewReceipt:
    """Confirm a framework-owned grade once; no client correctness is accepted by an API.

    Caller must load the immutable GradedReview from its authenticated server-side attempt.
    The expected version is captured at issuance, not freshly read at confirmation.
    """
    rating = Rating(rating)
    at = now or datetime.now(UTC)
    if at.tzinfo is None:
        raise ValueError("Review time must be timezone aware")
    at = at.astimezone(UTC)
    request_fingerprint = fingerprint(
        {
            "review": review.model_dump(mode="json"),
            "rating": int(rating),
        }
    )

    async def operation(txn: UUID) -> ReviewReceipt:
        previous = await repository.completed(db, owner, review.attempt_id, txn)
        if previous:
            if previous.get("request_fingerprint") != request_fingerprint:
                raise AppError(
                    "srs.attempt_conflict", 409, "Attempt has different completion data."
                )
            return ReviewReceipt.model_validate(previous["receipt"])
        sense = _decode(review.sense_id, "sense")
        project_id = _decode(review.project_id, "project")
        project = await repository.eligible_project(db, owner, project_id, sense, txn)
        memory = await repository.read_memory(db, owner, sense, txn)
        if memory is None:
            raise AppError("srs.not_found", 404, "Memory not found.")
        if memory.version != review.expected_version:
            raise AppError("srs.stale_review", 409, "Memory has already changed.")
        introduction = not memory.introduced
        await repository.check_daily_limit(db, owner, project, introduction, at, txn)
        prefs = await repository.preferences(db, owner, txn)
        review_time = at
        if memory.card.last_review is not None and review_time <= memory.card.last_review:
            review_time = memory.card.last_review + timedelta(microseconds=1)
        updated, _ = Scheduler(desired_retention=prefs.desired_retention).review_card(
            memory.card.to_card(),
            rating,
            review_datetime=review_time,
            review_duration=review.grade.duration_ms,
        )
        card = CardState.from_card(updated)
        result = ReviewReceipt(
            attempt_id=review.attempt_id,
            project_id=review.project_id,
            memory=MemoryRead(
                id=memory.id,
                sense_id=memory.sense_id,
                introduced=True,
                card=card,
            ),
            auto_rating=review.auto_rating,
            rating=rating,
            correct=review.grade.correct and not review.grade.gave_up,
            at=at,
            is_introduction=introduction,
        )
        await repository.save_review(
            db,
            owner,
            sense,
            card,
            {
                "owner": repository.user_record(owner),
                "memory": _decode(memory.id, "memory"),
                "project": project_id,
                "exercise": review.grade.exercise,
                "correct": result.correct,
                "hint_used": review.grade.hint_used,
                "duration_ms": review.grade.duration_ms,
                "auto_rating": int(review.auto_rating),
                "rating": int(rating),
                "at": at,
                "is_introduction": introduction,
                "attempt_id": review.attempt_id,
                "request_fingerprint": request_fingerprint,
                "receipt": result.model_dump(mode="json"),
            },
            txn,
        )
        return result

    return await _atomic(db, operation)
