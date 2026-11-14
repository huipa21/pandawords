from datetime import UTC, datetime

import pytest
from fsrs import Card, State

from app.core.errors import AppError
from app.domain.dictionary import DictionaryRecordRead
from app.domain.exercises import AnswerSpec, AttemptAnswer, ExerciseContext
from app.domain.srs import CardState, MemoryRead
from app.services.exercise_answers import grade_answer, normalize_answer, selected_lexeme_forms
from tests.exercise_support import FakeGenerator, plugins


def context() -> ExerciseContext:
    lemma = DictionaryRecordRead(id="lemma", table="lemma", owner=None, fields={"text": "Run"})
    lexeme = DictionaryRecordRead(
        id="lexeme",
        table="lexeme",
        owner=None,
        fields={"forms": [{"form": "running"}, {"form": "ran"}, {"form": "RUNNING"}]},
    )
    return ExerciseContext(
        owner="owner",
        project_id="project",
        sense_id="sense",
        lemma=lemma,
        lexeme=lexeme,
        sense=DictionaryRecordRead(id="sense", table="sense", owner=None, fields={}),
        forms=selected_lexeme_forms(lemma, lexeme),
    )


def memory(state: State, introduced: bool = True, stability: float = 6.99) -> MemoryRead:
    card = Card(state=state, stability=stability, due=datetime.now(UTC))
    return MemoryRead(
        id="memory", sense_id="sense", introduced=introduced, card=CardState.from_card(card)
    )


@pytest.mark.parametrize(
    "introduced,state",
    [
        (False, State.Review),
        (False, State.Learning),
        (True, State.Learning),
        (True, State.Relearning),
    ],
)
async def test_new_and_learning_only_use_recognition(introduced: bool, state: State) -> None:
    registry = plugins(FakeGenerator("recognize", "recognition"), FakeGenerator("recall", "recall"))
    result = await registry.select(context(), memory(state, introduced), random_value=lambda: 0)
    assert result.plugin.kind == "recognition"
    assert [(item.exercise, item.reason) for item in result.skipped] == [("recall", "card_state")]


@pytest.mark.parametrize(
    "stability,draw,kind",
    [
        (6.99, 0.4999, "recall"),
        (6.99, 0.5, "recognition"),
        (7, 0.6666, "recall"),
        (7, 2 / 3, "recognition"),
        (70, 0.6, "recall"),
    ],
)
async def test_kind_weights_not_distorted_by_plugin_count(stability, draw, kind) -> None:
    registry = plugins(
        FakeGenerator("recognize1", "recognition"),
        FakeGenerator("recognize2", "recognition"),
        FakeGenerator("recall", "recall"),
    )
    result = await registry.select(
        context(), memory(State.Review, stability=stability), random_value=lambda: draw
    )
    assert result.plugin.kind == kind


@pytest.mark.parametrize("kind", ["recall", "recognition"])
async def test_single_eligible_kind_and_missing_prerequisites(kind) -> None:
    other = "recognition" if kind == "recall" else "recall"
    registry = plugins(
        FakeGenerator("usable", kind), FakeGenerator("missing", other, "missing_audio")
    )
    result = await registry.select(context(), memory(State.Review), random_value=lambda: 0.9)
    assert result.plugin.kind == kind
    assert result.skipped[0].reason == "missing_audio"


async def test_no_usable_and_duplicate_registration() -> None:
    registry = plugins(FakeGenerator("missing", "recognition", "missing_distractors"))
    with pytest.raises(AppError, match="missing_distractors") as caught:
        await registry.select(context(), memory(State.Learning))
    assert caught.value.code == "exercise.no_usable"
    with pytest.raises(ValueError):
        registry.register(registry.get("missing"))
    with pytest.raises(AppError) as missing:
        registry.get("not_registered")
    assert missing.value.code == "exercise.unavailable"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("  ＲＵＮＮＩＮＧ \n", "running"),
        ("don’t", "don't"),
        ("Ice‑cream", "ice-cream"),
        (" \tlook   up\r\n", "look up"),
    ],
)
def test_deterministic_normalization(value: str, expected: str) -> None:
    assert normalize_answer(value) == expected
    assert normalize_answer(normalize_answer(value)) == expected


def test_selected_lexeme_forms_recall_and_separate_listening_restriction() -> None:
    selected = context()
    assert selected.forms == ("ran", "run", "running")
    private = AnswerSpec(answer="run", accepted_forms=selected.forms)
    assert grade_answer(private, " ＲＡＮ ").correct
    assert not grade_answer(private, "").correct
    assert not grade_answer(private, "runner").correct
    assert not grade_answer(private, "run!").correct
    listening = private.model_copy(update={"restriction": "audio_form", "answer": "running"})
    assert grade_answer(listening, " RUNNING ").correct
    assert not grade_answer(listening, "ran").correct
    choice = private.model_copy(update={"choice_id": "A"})
    assert grade_answer(choice, "A").correct
    assert not grade_answer(choice, "a").correct


@pytest.mark.parametrize("duration", [-1, 1.1, float("inf"), float("nan"), "4", True, None])
def test_duration_requires_finite_nonnegative_integer(duration) -> None:
    with pytest.raises(ValueError):
        AttemptAnswer(answer="a", duration_ms=duration)
