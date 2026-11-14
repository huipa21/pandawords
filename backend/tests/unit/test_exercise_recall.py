import pytest
from fsrs import State

from app.domain.exercises import ExerciseContext, GeneratedExercise, ListeningSource, Unavailable
from app.services import exercise_cloze, exercise_listen
from app.services.exercise_answers import grade_answer, selected_lexeme_forms
from app.services.exercise_registry import ExerciseRegistry
from tests.exercise_support import FakeGenerator, plugins
from tests.unit.test_exercise_framework import context, memory


def example(sentence: str) -> ExerciseContext:
    source = context()
    return source.model_copy(
        update={"sense": source.sense.model_copy(update={"fields": {"examples": [sentence]}})}
    )


@pytest.mark.parametrize("answer", ["run", "ran", "running", "runs", " RUN ", "\tRaN\n", "ＲＵＮ"])
async def test_cloze_accepts_selected_forms(answer: str) -> None:
    source = example("She was running; they ran, and we run.")
    source = source.model_copy(update={"forms": (*source.forms, "runs")})
    result = await exercise_cloze.generate(source)
    assert isinstance(result, GeneratedExercise)
    assert result.prompt.text == "she was ____; they ____, and we ____."
    assert grade_answer(result.private, answer).correct
    for wrong in ("run!", "walk", "runner", ""):
        assert not grade_answer(result.private, wrong).correct


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("A runner runs errands.", None),
        ("The runner can RUN.", "the runner can ____."),
        ("Run, run! (ran) running?", "____, ____! (____) ____?"),
        ("Bran and runningwater.", None),
    ],
)
async def test_cloze_word_boundaries_and_punctuation(sentence: str, expected: str | None) -> None:
    result = await exercise_cloze.generate(example(sentence))
    if expected is None:
        assert isinstance(result, Unavailable)
    else:
        assert isinstance(result, GeneratedExercise)
        assert result.prompt.text == expected


async def test_multiword_punctuation_and_normalization_contract() -> None:
    source = example("‘Mother‑in‑law’ and MOTHER-IN-LAW.")
    lemma = source.lemma.model_copy(update={"fields": {"text": "Mother-in-law"}})
    lexeme = source.lexeme.model_copy(update={"fields": {"forms": [{"form": "mothers-in-law"}]}})
    source = source.model_copy(
        update={"lemma": lemma, "lexeme": lexeme, "forms": selected_lexeme_forms(lemma, lexeme)}
    )
    result = await exercise_cloze.generate(source)
    assert isinstance(result, GeneratedExercise)
    assert result.prompt.text == "'____' and ____."
    assert grade_answer(result.private, "  MOTHERS‑IN‑LAW ").correct
    assert not grade_answer(result.private, "mother in law").correct
    source = example("They take \t off now.")
    source = source.model_copy(update={"forms": ("take off",)})
    result = await exercise_cloze.generate(source)
    assert isinstance(result, GeneratedExercise)
    assert result.prompt.text == "they ____ now."


@pytest.mark.parametrize("fields", [{}, {"examples": []}, {"examples": ["runner", 5, "They ran."]}])
async def test_invalid_examples_skipped(fields: dict) -> None:
    source = context()
    source = source.model_copy(update={"sense": source.sense.model_copy(update={"fields": fields})})
    result = await exercise_cloze.generate(source)
    assert isinstance(result, GeneratedExercise if fields.get("examples") else Unavailable)
    assert isinstance(
        await exercise_cloze.generate(source.model_copy(update={"forms": ()})), Unavailable
    )


async def test_listen_restricts_to_spoken_form_and_no_pregrade_key() -> None:
    async def source(context: ExerciseContext) -> ListeningSource | Unavailable:
        return ListeningSource(media_id="opaque", represented_form="Run")

    registry = ExerciseRegistry()
    exercise_listen.register(registry, source)
    plugin = registry.get("listen")
    result = await plugin.generate(context())
    assert isinstance(result, GeneratedExercise)
    assert result.prompt.model_dump() == {
        "text": "",
        "input": "text",
        "choices": (),
        "media_id": "opaque",
    }
    for answer in ("run", " RUN\t", "Ｒｕｎ"):
        assert plugin.grade(result.private, answer).correct
    for answer in ("ran", "running", "run!", "", "walk"):
        assert not plugin.grade(result.private, answer).correct


async def test_missing_recall_prerequisites_fall_back_independently() -> None:
    async def missing(context: ExerciseContext) -> ListeningSource | Unavailable:
        return Unavailable(exercise="listen", reason="missing_audio")

    registry = plugins(FakeGenerator("recognize", "recognition"))
    exercise_cloze.register(registry)
    exercise_listen.register(registry, missing)
    selected = await registry.select(
        example("They ran."), memory(State.Review), random_value=lambda: 0
    )
    assert selected.plugin.exercise == "cloze"
    assert [(item.exercise, item.reason) for item in selected.skipped] == [
        ("listen", "missing_audio")
    ]
    selected = await registry.select(
        example("No example."), memory(State.Review), random_value=lambda: 0
    )
    assert selected.plugin.exercise == "recognize"
    assert {item.exercise for item in selected.skipped} == {"cloze", "listen"}


async def test_missing_example_falls_back_to_listen_and_invalid_audio_form_skips() -> None:
    async def source(context: ExerciseContext) -> ListeningSource | Unavailable:
        return ListeningSource(media_id="opaque", represented_form="run")

    registry = ExerciseRegistry()
    exercise_cloze.register(registry)
    exercise_listen.register(registry, source)
    selected = await registry.select(
        example("Runner only."), memory(State.Review), random_value=lambda: 0
    )
    assert selected.plugin.exercise == "listen"
    assert selected.skipped == (Unavailable(exercise="cloze", reason="missing_example"),)
    plugin = registry.get("listen")
    assert isinstance(
        await plugin.generate(context().model_copy(update={"forms": ()})), Unavailable
    )
    assert isinstance(
        await plugin.generate(context().model_copy(update={"forms": ("walking",)})), Unavailable
    )
