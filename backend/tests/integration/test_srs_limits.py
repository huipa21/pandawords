import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fsrs import Rating
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db.dictionary_schema_test_support import visible
from app.db.memory_schema_test_support import owned
from app.db.srs import user_record
from app.db.srs_test_support import change_owner, seed_history
from app.domain.add_to_project import AddToProjectCreate
from app.domain.dictionary_keys import sense_key
from app.domain.project_tree import TreeTable
from app.domain.projects import ProjectCreate, ProjectPlan, ProjectUpdate
from app.services import project_tree, projects, srs
from app.services.add_to_project import add_to_project
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory
from tests.integration.srs_support import Study, create_study, graded

pytestmark = pytest.mark.integration


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def test_revalidates_hidden_ancestors_membership_and_cross_user_at_confirmation(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    other = await make_user()
    review = await graded(db, study)
    user = user_record(study.user.id)
    before = await srs.read_memory(db, study.user.id, study.sense_id)
    tree = await project_tree.read_tree(db, study.user.id, study.project.id, 1, 100, False)
    lemma = tree.items[0].lemma.id
    lexeme = tree.items[0].lexemes[0].lexeme.id
    targets: list[tuple[TreeTable, str]] = [
        ("lemma", lemma),
        ("lexeme", lexeme),
        ("sense", study.sense_id),
    ]
    for table, target in targets:
        await project_tree.set_visibility(
            db,
            study.user.id,
            study.project.id,
            table,
            target,
            True,
        )
        with pytest.raises(AppError) as rejected:
            await srs.apply_review(db, study.user.id, review, Rating.Good)
        assert rejected.value.code == "srs.not_eligible"
        assert await srs.read_memory(db, study.user.id, study.sense_id) == before
        await project_tree.set_visibility(
            db,
            study.user.id,
            study.project.id,
            table,
            target,
            False,
        )
    with pytest.raises(AppError) as rejected:
        await srs.apply_review(db, other.id, review, Rating.Good)
    assert rejected.value.status == 404
    assert await srs.reconcile_memberships(db, other.id) == 0
    assert await owned(db, "memory", user_record(other.id)) == []
    assert await owned(db, "review_log", user) == []
    await projects.delete_project(db, study.user.id, study.project.id)
    with pytest.raises(AppError) as rejected:
        await srs.apply_review(db, study.user.id, review, Rating.Good)
    assert rejected.value.status == 404
    assert await srs.read_memory(db, study.user.id, study.sense_id) == before


async def test_zero_new_then_unlimited_and_zero_review_cap_with_utc_counts(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    review = await graded(db, study)
    now = datetime(2026, 11, 14, 23, 59, tzinfo=UTC)
    await projects.update_project(
        db,
        study.user.id,
        study.project.id,
        ProjectUpdate(plan=ProjectPlan(daily_new=0)),
    )
    with pytest.raises(AppError) as rejected:
        await srs.apply_review(db, study.user.id, review, Rating.Good, now=now)
    assert rejected.value.code == "srs.daily_limit"
    await projects.update_project(
        db,
        study.user.id,
        study.project.id,
        ProjectUpdate(plan=ProjectPlan(daily_new=1)),
    )
    first = await srs.apply_review(db, study.user.id, review, Rating.Good, now=now)
    assert first.is_introduction
    # Introductions consume only new capacity, later reviews use only review capacity.
    second = await srs.apply_review(
        db,
        study.user.id,
        await graded(db, study),
        Rating.Good,
        now=now,
    )
    assert not second.is_introduction
    await projects.update_project(
        db,
        study.user.id,
        study.project.id,
        ProjectUpdate(plan=ProjectPlan(daily_new=0, review_cap=0)),
    )
    next_review = await graded(db, study)
    with pytest.raises(AppError) as rejected:
        await srs.apply_review(db, study.user.id, next_review, Rating.Good, now=now)
    assert rejected.value.code == "srs.daily_limit"
    await projects.update_project(
        db,
        study.user.id,
        study.project.id,
        ProjectUpdate(plan=ProjectPlan(daily_new=0, review_cap=1)),
    )
    with pytest.raises(AppError):
        await srs.apply_review(db, study.user.id, next_review, Rating.Good, now=now)
    midnight = now + timedelta(minutes=1)
    await srs.apply_review(db, study.user.id, next_review, Rating.Good, now=midnight)
    assert len(await owned(db, "review_log", user_record(study.user.id))) == 3


async def test_new_capacity_serialized_across_different_cards_and_projects(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    second_data = AddToProjectCreate(
        lemma_key=["en", "decision"],
        selected_senses=[sense_key("en", "decision", "noun", source_sense_id="decision-choice")],
    )
    # Use the fixture's authoritative sense identity rather than assuming source spelling.
    lexemes = await lexicon_reader.lexemes(["en", "decision"])
    senses = await lexicon_reader.senses(lexemes[0].id)
    second_data.selected_senses = [senses[0].id]
    result = await add_to_project(db, lexicon_reader, study.user.id, study.project.id, second_data)
    second = Study(study.user, study.project, result.selected_sense_ids[0], second_data)
    await projects.update_project(
        db,
        study.user.id,
        study.project.id,
        ProjectUpdate(plan=ProjectPlan(daily_new=1)),
    )
    first_review, second_review = await graded(db, study), await graded(db, second)
    now = datetime(2026, 11, 14, 23, 59, tzinfo=UTC)
    results = await asyncio.gather(
        srs.apply_review(db, study.user.id, first_review, Rating.Good, now=now),
        srs.apply_review(db, study.user.id, second_review, Rating.Good, now=now),
        return_exceptions=True,
    )
    errors = [result for result in results if isinstance(result, AppError)]
    assert len(errors) == 1 and errors[0].code == "srs.daily_limit"
    assert len(await owned(db, "review_log", user_record(study.user.id))) == 1
    losing = first_review if isinstance(results[0], AppError) else second_review
    await srs.apply_review(
        db,
        study.user.id,
        losing,
        Rating.Good,
        now=now + timedelta(minutes=1),
    )
    # Reviewing an already-introduced shared card in another project uses review capacity.
    third_project = await projects.create_project(
        db,
        study.user.id,
        ProjectCreate(name="Third", plan=ProjectPlan(daily_new=0, review_cap=1)),
    )
    await add_to_project(db, lexicon_reader, study.user.id, third_project.id, study.data)
    study.project = third_project
    third = await srs.apply_review(db, study.user.id, await graded(db, study), Rating.Good, now=now)
    assert not third.is_introduction
    assert third.project_id == third_project.id
    with pytest.raises(AppError) as rejected:
        await srs.apply_review(db, study.user.id, await graded(db, study), Rating.Good, now=now)
    assert rejected.value.code == "srs.daily_limit"
    logs = await owned(db, "review_log", user_record(study.user.id))
    assert sum(log["project"] == decode_rid(third_project.id, "project") for log in logs) == 1


async def test_history_uses_only_last_100_completed_correct_same_user_and_type(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    other = await create_study(db, make_user, lexicon_reader)
    memory = await srs.read_memory(db, study.user.id, study.sense_id)
    other_memory = await srs.read_memory(db, other.user.id, other.sense_id)
    assert (await graded(db, study, duration=5999)).auto_rating == Rating.Good
    await seed_history(db, study.user.id, memory, study.project.id, "cloze", [10000] * 19)
    await seed_history(db, study.user.id, memory, study.project.id, "listen", [100] * 25)
    await seed_history(db, other.user.id, other_memory, other.project.id, "cloze", [100] * 25)
    await seed_history(
        db,
        study.user.id,
        memory,
        study.project.id,
        "cloze",
        [100] * 25,
        correct=False,
    )
    assert (await graded(db, study, duration=5999)).auto_rating == Rating.Good
    await seed_history(db, study.user.id, memory, study.project.id, "cloze", [10000])
    assert (await graded(db, study, duration=5999)).auto_rating == Rating.Easy
    assert (await graded(db, study, exercise="listen", duration=5999)).auto_rating == Rating.Hard
    assert (await graded(db, other, duration=5999)).auto_rating == Rating.Hard
    # Older outliers are excluded by the 100-row bound, rather than averaged into thresholds.
    old = datetime(2020, 1, 1, tzinfo=UTC)
    await seed_history(db, study.user.id, memory, study.project.id, "cloze", [100] * 110, at=old)
    await seed_history(db, study.user.id, memory, study.project.id, "cloze", [10000] * 80)
    assert (await graded(db, study, duration=5999)).auto_rating == Rating.Easy


async def test_revalidates_current_dictionary_and_edge_ownership(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    other = await make_user()
    user, foreign = user_record(study.user.id), user_record(other.id)
    before = await srs.read_memory(db, study.user.id, study.sense_id)
    review = await graded(db, study)
    sense = decode_rid(study.sense_id, "sense")
    edge = next(row for row in await visible(db, "has_sense", user) if row["out"] == sense)
    for target in [sense, edge["in"], edge["id"]]:
        await change_owner(db, target, None, foreign)
        with pytest.raises(AppError) as rejected:
            await srs.apply_review(db, study.user.id, review, Rating.Good)
        assert rejected.value.code == "srs.not_eligible"
        assert await srs.read_memory(db, study.user.id, study.sense_id) == before
        assert await owned(db, "review_log", user) == []
        await change_owner(db, target, foreign, None)
