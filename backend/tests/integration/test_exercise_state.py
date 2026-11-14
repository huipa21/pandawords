import asyncio
from typing import cast

import pytest
from fsrs import Rating
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError
from app.db import exercise_test_support as probe
from app.db import exercises as repository
from app.domain.exercises import AttemptCreate, AttemptGraded
from app.domain.overrides import Form, OverrideFields, OverrideUpdate
from app.domain.project_tree import TreeTable
from app.services import exercise_attempts as attempts
from app.services import overrides, project_tree, projects, srs
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory
from tests.exercise_support import Clock, FakeGenerator, plugins
from tests.integration.srs_support import create_study, graded

pytestmark = pytest.mark.integration


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(attempts, "_now", clock.now)
    return clock


def fake():
    return plugins(FakeGenerator("fake", "recognition"))


@pytest.mark.parametrize("is_graded", [False, True])
async def test_expiry_all_active_operations_do_not_review(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    clock: Clock,
    is_graded: bool,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    registry = fake()
    opened = await attempts.create_attempt(
        db,
        study.user.id,
        AttemptCreate(project_id=study.project.id, sense_id=study.sense_id),
        plugins=registry,
    )
    if is_graded:
        await attempts.submit(db, Settings(), study.user.id, opened.id, "a", 1000, plugins=registry)
    clock.advance(1800)
    for operation in (
        attempts.read_attempt(db, study.user.id, opened.id),
        attempts.submit(db, Settings(), study.user.id, opened.id, "a", 1000, plugins=registry),
        attempts.confirm(db, study.user.id, opened.id, Rating.Good),
    ):
        with pytest.raises(AppError) as caught:
            await operation
        assert caught.value.code == (
            "exercise.not_graded"
            if not is_graded and "Grade" in caught.value.message
            else "exercise.expired"
        )
    if not is_graded:
        with pytest.raises(AppError) as caught:
            await attempts.request_hint(db, study.user.id, opened.id)
        assert caught.value.code == "exercise.expired"
    assert not (await srs.read_memory(db, study.user.id, study.sense_id)).introduced
    assert await probe.logs(db, study.user.id) == []


@pytest.mark.parametrize("target", ["lemma", "lexeme", "sense", "removed", "deleted"])
async def test_changed_eligibility_blocks_open_and_graded_attempts(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    clock: Clock,
    target: str,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    registry = fake()
    data = AttemptCreate(project_id=study.project.id, sense_id=study.sense_id)
    open_attempt = await attempts.create_attempt(db, study.user.id, data, plugins=registry)
    graded_attempt = await attempts.create_attempt(db, study.user.id, data, plugins=registry)
    await attempts.submit(
        db, Settings(), study.user.id, graded_attempt.id, "a", 1000, plugins=registry
    )
    tree = await project_tree.read_tree(db, study.user.id, study.project.id, 1, 20, False)
    branch = tree.items[0]
    ids = {"lemma": branch.lemma.id, "lexeme": branch.lexemes[0].lexeme.id, "sense": study.sense_id}
    if target == "removed":
        await probe.remove_membership(db, study.user.id, study.project.id, study.sense_id)
    elif target == "deleted":
        await projects.delete_project(db, study.user.id, study.project.id)
    else:
        await project_tree.set_visibility(
            db, study.user.id, study.project.id, cast(TreeTable, target), ids[target], True
        )
    before = await srs.read_memory(db, study.user.id, study.sense_id)
    for operation in (
        attempts.create_attempt(db, study.user.id, data, plugins=registry),
        attempts.read_attempt(db, study.user.id, open_attempt.id),
        attempts.request_hint(db, study.user.id, open_attempt.id),
        attempts.submit(
            db, Settings(), study.user.id, open_attempt.id, "a", 1000, plugins=registry
        ),
        attempts.confirm(db, study.user.id, graded_attempt.id, Rating.Good),
    ):
        with pytest.raises(AppError) as caught:
            await operation
        assert caught.value.code in {"srs.not_eligible", "project.not_found"}
    assert await srs.read_memory(db, study.user.id, study.sense_id) == before
    assert await probe.logs(db, study.user.id) == []


async def test_stale_issuance_does_not_overwrite_newer_memory(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    clock: Clock,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    registry = fake()
    data = AttemptCreate(project_id=study.project.id, sense_id=study.sense_id)
    open_attempt = await attempts.create_attempt(db, study.user.id, data, plugins=registry)
    graded_attempt = await attempts.create_attempt(db, study.user.id, data, plugins=registry)
    await attempts.submit(
        db, Settings(), study.user.id, graded_attempt.id, "a", 1000, plugins=registry
    )
    receipt = await srs.apply_review(db, study.user.id, await graded(db, study), Rating.Good)
    for operation in (
        attempts.read_attempt(db, study.user.id, open_attempt.id),
        attempts.request_hint(db, study.user.id, open_attempt.id),
        attempts.submit(
            db, Settings(), study.user.id, open_attempt.id, "a", 1000, plugins=registry
        ),
        attempts.confirm(db, study.user.id, graded_attempt.id, Rating.Good),
    ):
        with pytest.raises(AppError) as caught:
            await operation
        assert caught.value.code == "exercise.stale"
    assert await srs.read_memory(db, study.user.id, study.sense_id) == receipt.memory
    assert len(await probe.logs(db, study.user.id)) == 1


async def test_concurrent_conflicting_answers_and_hints_are_serialized(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    clock: Clock,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    registry = fake()
    opened = await attempts.create_attempt(
        db,
        study.user.id,
        AttemptCreate(project_id=study.project.id, sense_id=study.sense_id),
        plugins=registry,
    )
    results = await asyncio.gather(
        attempts.submit(db, Settings(), study.user.id, opened.id, "a", 1000, plugins=registry),
        attempts.submit(db, Settings(), study.user.id, opened.id, "b", 1000, plugins=registry),
        attempts.request_hint(db, study.user.id, opened.id),
        return_exceptions=True,
    )
    answers = results[:2]
    assert sum(isinstance(result, AttemptGraded) for result in answers) == 1
    assert (
        sum(
            isinstance(result, AppError) and result.code == "exercise.answer_conflict"
            for result in answers
        )
        == 1
    )
    saved = await probe.saved(db, study.user.id, opened.id)
    assert saved.review is not None
    assert saved.review.grade.hint_used == saved.hint_used
    if isinstance(results[2], AppError):
        assert results[2].code == "exercise.not_open"
        assert not saved.hint_used
    else:
        assert saved.hint_used
    assert await probe.logs(db, study.user.id) == []


async def test_durable_receipt_repairs_crash_before_attempt_confirmation_write(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    registry = fake()
    opened = await attempts.create_attempt(
        db,
        study.user.id,
        AttemptCreate(project_id=study.project.id, sense_id=study.sense_id),
        plugins=registry,
    )
    await attempts.submit(db, Settings(), study.user.id, opened.id, "a", 1000, plugins=registry)
    original = repository.write

    async def crash(*args, **kwargs):
        raise RuntimeError("simulated interrupted attempt commit")

    monkeypatch.setattr(repository, "write", crash)
    with pytest.raises(RuntimeError, match="interrupted"):
        await attempts.confirm(db, study.user.id, opened.id, Rating.Easy)
    assert (await probe.saved(db, study.user.id, opened.id)).status == "graded"
    assert len(await probe.logs(db, study.user.id)) == 1
    monkeypatch.setattr(repository, "write", original)
    clock.advance(1900)
    await projects.delete_project(db, study.user.id, study.project.id)
    receipt = await attempts.confirm(db, study.user.id, opened.id, Rating.Easy)
    assert receipt.status == "confirmed"
    with pytest.raises(AppError) as caught:
        await attempts.confirm(db, study.user.id, opened.id, Rating.Good)
    assert caught.value.code == "srs.attempt_conflict"
    assert len(await probe.logs(db, study.user.id)) == 1


async def test_form_lookup_uses_only_selected_effective_lexeme_and_owner_overlay(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    clock: Clock,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    other = await make_user()
    tree = await project_tree.read_tree(db, study.user.id, study.project.id, 1, 20, False)
    lexeme = tree.items[0].lexemes[0].lexeme.id
    await overrides.write(
        db,
        other.id,
        "lexeme",
        lexeme,
        OverrideUpdate(fields=OverrideFields(forms=[Form(form="foreign-form")])),
        action="put",
    )
    await overrides.write(
        db,
        study.user.id,
        "lexeme",
        lexeme,
        OverrideUpdate(fields=OverrideFields(forms=[Form(form="ran"), Form(form="running")])),
        action="put",
    )
    # Introduce once so recall becomes eligible.
    await srs.apply_review(db, study.user.id, await graded(db, study), Rating.Easy)
    registry = plugins(FakeGenerator("fake_recall", "recall"))
    data = AttemptCreate(project_id=study.project.id, sense_id=study.sense_id)
    opened = await attempts.create_attempt(db, study.user.id, data, plugins=registry)
    private = (await probe.saved(db, study.user.id, opened.id)).generated.private
    assert private.accepted_forms == ("ran", "run", "running")
    result = await attempts.submit(
        db, Settings(), study.user.id, opened.id, " ＲＡＮ ", 1000, plugins=registry
    )
    assert isinstance(result, AttemptGraded) and result.feedback.correct


@pytest.mark.parametrize("duration", [-1, 1.1, float("inf"), float("nan"), True])
async def test_service_rejects_invalid_duration_before_touching_attempt(
    db: AsyncSurrealConnection,
    duration,
) -> None:
    with pytest.raises(AppError) as caught:
        await attempts.submit(db, Settings(), "not_an_owner", "missing", "a", duration)
    assert caught.value.code == "exercise.invalid_duration"
