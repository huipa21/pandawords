import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fsrs import Rating
from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import srs as repository
from app.db.memory_schema_test_support import owned
from app.db.srs import user_record
from app.domain.projects import ProjectCreate
from app.domain.srs import CardState, SrsPreferences
from app.services import projects, srs
from app.services.add_to_project import add_to_project
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory
from tests.integration.srs_support import create_study, graded

pytestmark = pytest.mark.integration


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def test_identical_retry_concurrency_stale_conflict_and_durable_receipt(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    review, stale = await graded(db, study), await graded(db, study)
    receipts = await asyncio.gather(
        *[srs.apply_review(db, study.user.id, review, Rating.Easy) for _ in range(3)],
    )
    assert receipts[0] == receipts[1] == receipts[2]
    assert receipts[0].auto_rating == Rating.Good and receipts[0].rating == Rating.Easy
    assert await srs.read_memory(db, study.user.id, study.sense_id) == receipts[0].memory
    assert len(await owned(db, "review_log", user_record(study.user.id))) == 1
    with pytest.raises(AppError, match="different completion"):
        await srs.apply_review(db, study.user.id, review, Rating.Hard)
    altered = review.model_copy(
        update={
            "grade": review.grade.model_copy(update={"hint_used": True}),
        }
    )
    with pytest.raises(AppError, match="different completion"):
        await srs.apply_review(db, study.user.id, altered, Rating.Easy)
    with pytest.raises(AppError, match="already changed"):
        await srs.apply_review(db, study.user.id, stale, Rating.Good)
    next_review = await graded(db, study, correct=False)
    await srs.apply_review(
        db,
        study.user.id,
        next_review,
        Rating.Again,
        now=receipts[0].at + timedelta(days=2),
    )
    assert await srs.apply_review(db, study.user.id, review, Rating.Easy) == receipts[0]
    logs = await owned(db, "review_log", user_record(study.user.id))
    assert len(logs) == 2
    assert sorted(log["is_introduction"] for log in logs) == [False, True]


async def test_distinct_concurrent_attempts_reject_stale_update(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    first, second = await graded(db, study), await graded(db, study)
    results = await asyncio.gather(
        srs.apply_review(db, study.user.id, first, Rating.Good),
        srs.apply_review(db, study.user.id, second, Rating.Easy),
        return_exceptions=True,
    )
    errors = [result for result in results if isinstance(result, AppError)]
    assert len(errors) == 1 and errors[0].code == "srs.stale_review"
    assert len(await owned(db, "review_log", user_record(study.user.id))) == 1


async def test_log_failure_rolls_back_card_and_project(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    before = await srs.read_memory(db, study.user.id, study.sense_id)
    review = await graded(db, study)
    original = repository.save_review

    async def fail_after_write(
        connection: AsyncSurrealConnection,
        owner: str,
        sense: RecordID,
        card: CardState,
        log: dict,
        txn: UUID,
    ) -> None:
        await original(connection, owner, sense, card, log, txn)
        raise RuntimeError("log failure")

    with monkeypatch.context() as patch:
        patch.setattr(repository, "save_review", fail_after_write)
        with pytest.raises(RuntimeError, match="log failure"):
            await srs.apply_review(db, study.user.id, review, Rating.Good)
    assert await srs.read_memory(db, study.user.id, study.sense_id) == before
    assert await owned(db, "review_log", user_record(study.user.id)) == []
    assert await projects.read_project(db, study.user.id, study.project.id) == study.project
    await srs.apply_review(db, study.user.id, review, Rating.Good)


async def test_manual_easy_after_recognition_shared_card_retention_and_project_deletion(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    other = await create_study(db, make_user, lexicon_reader)
    await srs.update_preferences(db, study.user.id, SrsPreferences(desired_retention=0.99))
    assert (await srs.read_preferences(db, other.user.id)).desired_retention == 0.9
    now = datetime(2026, 11, 14, tzinfo=UTC)
    review = await graded(db, study, exercise="def2word", kind="recognition", duration=1)
    receipt = await srs.apply_review(db, study.user.id, review, Rating.Easy, now=now)
    other_receipt = await srs.apply_review(
        db, other.user.id, await graded(db, other), Rating.Easy, now=now
    )
    assert receipt.auto_rating == Rating.Good and receipt.rating == Rating.Easy
    assert receipt.correct and receipt.memory.card.due < other_receipt.memory.card.due
    second = await projects.create_project(db, study.user.id, ProjectCreate(name="Second"))
    await add_to_project(db, lexicon_reader, study.user.id, second.id, study.data)
    assert await srs.read_memory(db, study.user.id, study.sense_id) == receipt.memory
    study.project = second
    subsequent = await srs.apply_review(
        db,
        study.user.id,
        await graded(db, study),
        Rating.Good,
        now=now + timedelta(days=1),
    )
    assert not subsequent.is_introduction
    await projects.delete_project(db, study.user.id, second.id)
    assert await srs.read_memory(db, study.user.id, study.sense_id) == subsequent.memory
    assert await srs.apply_review(db, study.user.id, review, Rating.Easy) == receipt
    logs = await owned(db, "review_log", user_record(study.user.id))
    assert len(logs) == 2
    assert {log["project"] for log in logs} == {
        decode_rid(review.project_id, "project"),
        decode_rid(second.id, "project"),
    }


@pytest.mark.parametrize(
    ("correct", "gave_up", "hint_used", "auto"),
    [
        (False, False, False, Rating.Again),
        (True, True, False, Rating.Again),
        (True, False, True, Rating.Hard),
    ],
)
async def test_manual_override_preserves_framework_outcome_and_capped_duration(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    correct: bool,
    gave_up: bool,
    hint_used: bool,
    auto: Rating,
) -> None:
    from uuid import uuid4

    from app.core.config import Settings
    from app.domain.srs import FrameworkGrade

    study = await create_study(db, make_user, lexicon_reader)
    before = await srs.read_memory(db, study.user.id, study.sense_id)
    review = await srs.grade_review(
        db,
        Settings(),
        study.user.id,
        attempt_id=uuid4().hex,
        project_id=study.project.id,
        sense_id=study.sense_id,
        expected_version=before.version,
        grade=FrameworkGrade(
            exercise="def2word",
            kind="recognition",
            correct=correct,
            gave_up=gave_up,
            hint_used=hint_used,
            duration_ms=90000,
        ),
    )
    receipt = await srs.apply_review(db, study.user.id, review, Rating.Easy)
    assert receipt.auto_rating == auto and receipt.rating == Rating.Easy
    assert receipt.correct == (correct and not gave_up)
    log = (await owned(db, "review_log", user_record(study.user.id)))[0]
    assert log["correct"] == receipt.correct
    assert log["auto_rating"] == int(auto) and log["rating"] == 4
    assert log["duration_ms"] == 60000 and log["hint_used"] == hint_used
