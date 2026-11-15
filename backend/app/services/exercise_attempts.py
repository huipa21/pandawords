"""Durable open → graded → confirmed attempts; only the last step schedules memory."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fsrs import Rating
from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import exercises as repository
from app.db import srs as cards
from app.db.auth import _atomic
from app.db.exercise_context import selected_context
from app.domain.exercises import (
    Attempt,
    AttemptConfirmed,
    AttemptCreate,
    AttemptGraded,
    AttemptOpen,
    AttemptRead,
    ExerciseContext,
    ExerciseFeedback,
)
from app.domain.srs import FrameworkGrade, fingerprint
from app.services import review_preferences, srs
from app.services.exercise_answers import selected_lexeme_forms
from app.services.exercise_registry import ExerciseRegistry, registry

ATTEMPT_TTL = timedelta(minutes=30)


def _now() -> datetime:
    return datetime.now(UTC)


def _decode(value: str, table: str) -> RecordID:
    try:
        return decode_rid(value, table)
    except ValueError:
        raise AppError("exercise.not_found", 404, "Study record not found.") from None


def public(attempt: Attempt) -> AttemptRead:
    data = {
        "id": attempt.id,
        "project_id": attempt.project_id,
        "sense_id": attempt.sense_id,
        "exercise": attempt.exercise,
        "kind": attempt.kind,
        "status": attempt.status,
        "prompt": attempt.generated.prompt,
        "issued_at": attempt.issued_at,
        "expires_at": attempt.expires_at,
        "hint_used": attempt.hint_used,
        "hint": attempt.generated.private.hint if attempt.hint_used else None,
        "skipped": attempt.skipped,
    }
    if attempt.status == "open":
        return AttemptOpen.model_validate(data)
    if attempt.review is None or attempt.feedback is None:
        raise RuntimeError("Graded attempt is missing its immutable review")
    data.update(
        feedback=attempt.feedback,
        auto_rating=attempt.review.auto_rating,
        duration_ms=attempt.review.grade.duration_ms,
        server_elapsed_ms=attempt.server_elapsed_ms,
    )
    if attempt.status == "confirmed":
        return AttemptConfirmed.model_validate({**data, "receipt": attempt.receipt})
    return AttemptGraded.model_validate(data)


async def _active(db: AsyncSurrealConnection, attempt: Attempt, txn: UUID) -> None:
    if _now() >= attempt.expires_at:
        raise AppError("exercise.expired", 410, "Attempt has expired.")
    project, sense = _decode(attempt.project_id, "project"), _decode(attempt.sense_id, "sense")
    await cards.eligible_project(db, attempt.owner, project, sense, txn)
    memory = await cards.read_memory(db, attempt.owner, sense, txn)
    if memory is None or memory.version != attempt.expected_version:
        raise AppError("exercise.stale", 409, "Memory changed after attempt issuance.")


async def create_attempt(
    db: AsyncSurrealConnection,
    owner: str,
    data: AttemptCreate,
    *,
    plugins: ExerciseRegistry = registry,
    ttl: timedelta = ATTEMPT_TTL,
) -> AttemptRead:
    project, sense = _decode(data.project_id, "project"), _decode(data.sense_id, "sense")

    async def context_operation(txn: UUID) -> ExerciseContext:
        return await selected_context(db, owner, project, sense, txn)

    context = await _atomic(db, context_operation)
    context = context.model_copy(
        update={"forms": selected_lexeme_forms(context.lemma, context.lexeme)}
    )
    memory = await srs.read_memory(db, owner, data.sense_id)
    prefs = await review_preferences.read(db, owner)
    disabled = frozenset(
        exercise
        for exercise, enabled in (
            ("image2word", prefs.review_images_enabled),
            ("listen", prefs.review_audio_enabled),
        )
        if not enabled
    )
    selection = await plugins.select(context, memory, disabled=disabled)
    issued = _now()
    attempt = Attempt(
        id=uuid4().hex,
        owner=owner,
        project_id=data.project_id,
        sense_id=data.sense_id,
        exercise=selection.plugin.exercise,
        kind=selection.plugin.kind,
        generated=selection.generated,
        expected_version=memory.version,
        issued_at=issued,
        expires_at=issued + ttl,
        skipped=selection.skipped,
    )

    async def operation(txn: UUID) -> AttemptRead:
        await _active(db, attempt, txn)
        await repository.write(db, attempt, txn, create=True)
        return public(attempt)

    return await _atomic(db, operation)


async def read_attempt(db: AsyncSurrealConnection, owner: str, attempt_id: str) -> AttemptRead:
    async def operation(txn: UUID) -> AttemptRead:
        attempt = await repository.read(db, owner, attempt_id, txn)
        if attempt.status != "confirmed":
            await _active(db, attempt, txn)
        return public(attempt)

    return await _atomic(db, operation)


async def request_hint(db: AsyncSurrealConnection, owner: str, attempt_id: str) -> AttemptRead:
    async def operation(txn: UUID) -> AttemptRead:
        attempt = await repository.read(db, owner, attempt_id, txn)
        if attempt.status != "open":
            raise AppError("exercise.not_open", 409, "Hints require an open attempt.")
        await _active(db, attempt, txn)
        if attempt.generated.private.hint is None:
            raise AppError("exercise.hint_unavailable", 409, "No hint is available.")
        attempt = attempt.model_copy(update={"hint_used": True})
        await repository.write(db, attempt, txn)
        return public(attempt)

    return await _atomic(db, operation)


async def submit(
    db: AsyncSurrealConnection,
    settings: Settings,
    owner: str,
    attempt_id: str,
    answer: str | None,
    duration_ms: int,
    *,
    plugins: ExerciseRegistry = registry,
    client_key: str | None = None,
) -> AttemptRead:
    if type(duration_ms) is not int or duration_ms < 0:
        raise AppError("exercise.invalid_duration", 422, "Duration must be a nonnegative integer.")
    # A retry identity binds the single grade to one queued client answer.
    identity = {"answer": answer, "duration_ms": duration_ms}
    submission = fingerprint(
        identity if client_key is None else {**identity, "client_key": client_key}
    )

    async def operation(txn: UUID) -> AttemptRead:
        attempt = await repository.read(db, owner, attempt_id, txn)
        if attempt.status == "confirmed":
            if attempt.submission != submission:
                raise AppError("exercise.answer_conflict", 409, "Attempt already has an answer.")
            return public(attempt)
        await _active(db, attempt, txn)
        if attempt.status == "graded":
            if attempt.submission != submission:
                raise AppError("exercise.answer_conflict", 409, "Attempt already has an answer.")
            return public(attempt)
        plugin = plugins.get(attempt.exercise)
        feedback = (
            ExerciseFeedback(correct=False, answer=attempt.generated.private.answer)
            if answer is None
            else plugin.grade(attempt.generated.private, answer)
        )
        server_elapsed = max(0, int((_now() - attempt.issued_at).total_seconds() * 1000))
        grade = FrameworkGrade(
            exercise=attempt.exercise,
            kind=attempt.kind,
            correct=feedback.correct,
            gave_up=answer is None,
            hint_used=attempt.hint_used,
            duration_ms=min(duration_ms, server_elapsed, 60000),
        )
        review = await srs.grade_review(
            db,
            settings,
            owner,
            attempt_id=attempt.id,
            project_id=attempt.project_id,
            sense_id=attempt.sense_id,
            expected_version=attempt.expected_version,
            grade=grade,
        )
        attempt = attempt.model_copy(
            update={
                "status": "graded",
                "submission": submission,
                "feedback": feedback,
                "review": review,
                "server_elapsed_ms": server_elapsed,
            }
        )
        await repository.write(db, attempt, txn)
        return public(attempt)

    return await _atomic(db, operation)


async def confirm(
    db: AsyncSurrealConnection,
    owner: str,
    attempt_id: str,
    rating: Rating,
) -> AttemptRead:
    async def load(txn: UUID) -> Attempt:
        attempt = await repository.read(db, owner, attempt_id, txn)
        if attempt.status == "open" or attempt.review is None:
            raise AppError("exercise.not_graded", 409, "Grade an answer before confirming.")
        # The atomic SRS receipt also repairs a crash between review and attempt commits.
        completed = await cards.completed(db, owner, attempt.id, txn)
        if completed is None:
            await _active(db, attempt, txn)
        return attempt

    attempt = await _atomic(db, load)
    assert attempt.review is not None
    receipt = await srs.apply_review(db, owner, attempt.review, rating)

    async def finish(txn: UUID) -> AttemptRead:
        current = await repository.read(db, owner, attempt_id, txn)
        current = current.model_copy(update={"status": "confirmed", "receipt": receipt})
        await repository.write(db, current, txn)
        return public(current)

    return await _atomic(db, finish)
