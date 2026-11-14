from dataclasses import dataclass

import pytest
from fsrs import State

from app.domain.distractors import ChoiceLabel
from app.domain.exercises import (
    Choice,
    DistractorCandidates,
    ExerciseContext,
    GeneratedExercise,
    Unavailable,
)
from app.domain.recognition import RelationQuestion
from app.services import recognition
from app.services.exercise_registry import ExerciseRegistry
from tests.unit.test_exercise_framework import context, memory


@dataclass
class Provider:
    unavailable: bool = False
    related: bool = True

    async def choices(
        self, selected: ExerciseContext, *, label: ChoiceLabel = "word"
    ) -> DistractorCandidates | Unavailable:
        if self.unavailable:
            return Unavailable(exercise="provider", reason="insufficient_safe_distractors")
        return DistractorCandidates(
            answer_choice_id=selected.sense_id,
            choices=(
                Choice(id=selected.sense_id, label="run" if label == "word" else "move on foot"),
                Choice(id="other", label="walk" if label == "word" else "move slowly"),
                Choice(id="duplicate", label="ＷＡＬＫ" if label == "word" else " MOVE SLOWLY "),
            ),
        )

    async def relations(self, selected: ExerciseContext) -> tuple[RelationQuestion, ...]:
        if not self.related:
            return ()
        return (RelationQuestion(text="Synonym of sprint?", answer=selected),)


def selected(*, pron: bool = True, gloss: bool = False) -> ExerciseContext:
    result = context()
    return result.model_copy(
        update={
            "sense": result.sense.model_copy(
                update={
                    "fields": {"gloss": {"zh": "跑"}} if gloss else {"definition": "move on foot"}
                }
            ),
            "lexeme": result.lexeme.model_copy(
                update={
                    "fields": {
                        **result.lexeme.fields,
                        "pos": "verb",
                        "pron": [{"accent": "UK", "ipa": "/rʌn/"}] if pron else [],
                    }
                }
            ),
        }
    )


@pytest.mark.parametrize("exercise", ["def2word", "word2def", "relation"])
async def test_registered_recognition_opaque_unique_options_and_grading(exercise: str) -> None:
    target = ExerciseRegistry()
    recognition.register(target, Provider())
    plugin = target.get(exercise)
    assert plugin.kind == "recognition"
    generated = await plugin.generate(selected())
    assert isinstance(generated, GeneratedExercise)
    assert len(generated.prompt.choices) == 2
    assert len({item.id for item in generated.prompt.choices}) == 2
    assert len({item.label for item in generated.prompt.choices}) == 2
    assert all(len(item.id) == 32 for item in generated.prompt.choices)
    assert all(item.id not in {"sense", "other", "duplicate"} for item in generated.prompt.choices)
    assert plugin.grade(generated.private, generated.private.choice_id or "").correct
    wrong = next(
        item.id for item in generated.prompt.choices if item.id != generated.private.choice_id
    )
    assert not plugin.grade(generated.private, wrong).correct
    assert not plugin.grade(generated.private, generated.private.answer).correct
    public = generated.prompt.model_dump_json()
    assert "choice_id" not in public and "answer_choice_id" not in public
    again = await plugin.generate(selected())
    assert isinstance(again, GeneratedExercise)
    assert again.private.choice_id != generated.private.choice_id


@pytest.mark.parametrize("pron", [True, False])
async def test_pronunciation_is_optional_and_selected_sense_gloss_is_effective(pron: bool) -> None:
    target = ExerciseRegistry()
    recognition.register(target, Provider())
    result = await target.get("word2def").generate(selected(pron=pron))
    assert isinstance(result, GeneratedExercise)
    assert "Run (verb)" in result.prompt.text
    assert ("UK: /rʌn/" in result.prompt.text) == pron
    gloss = await target.get("def2word").generate(selected(gloss=True))
    assert isinstance(gloss, GeneratedExercise) and gloss.prompt.text == "跑"


async def test_registry_falls_back_when_relations_missing() -> None:
    target = ExerciseRegistry()
    recognition.register(target, Provider(related=False))
    result = await target.select(selected(), memory(State.Learning), random_value=lambda: 0.99)
    assert result.plugin.exercise == "word2def"
    assert result.skipped[0].exercise == "relation"
    for exercise in ("def2word", "word2def"):
        missing = await target.get(exercise).generate(context())
        assert isinstance(missing, Unavailable)


@pytest.mark.parametrize("exercise", ["def2word", "word2def", "relation"])
async def test_insufficient_distractors_are_unavailable(exercise: str) -> None:
    target = ExerciseRegistry()
    recognition.register(target, Provider(unavailable=True))
    result = await target.get(exercise).generate(selected())
    assert isinstance(result, Unavailable) and result.exercise == exercise


async def test_relation_removes_other_valid_relation_answers() -> None:
    class Ambiguous(Provider):
        async def relations(self, selected: ExerciseContext) -> tuple[RelationQuestion, ...]:
            return (
                RelationQuestion(
                    text="Synonym of sprint?", answer=selected, excluded_words=("walk",)
                ),
            )

    target = ExerciseRegistry()
    recognition.register(target, Ambiguous())
    result = await target.get("relation").generate(selected())
    assert isinstance(result, Unavailable)
