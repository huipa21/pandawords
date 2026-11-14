"""Offline cloze generation from the selected sense's effective examples."""

import re

from app.domain.exercises import (
    AnswerSpec,
    ExerciseContext,
    ExercisePrompt,
    GeneratedExercise,
    Unavailable,
)
from app.services.exercise_answers import grade_answer, normalize_answer
from app.services.exercise_registry import ExercisePlugin, ExerciseRegistry


async def generate(context: ExerciseContext) -> GeneratedExercise | Unavailable:
    forms = tuple(
        sorted(
            {normalize_answer(form) for form in context.forms if normalize_answer(form)},
            key=lambda form: (-len(form), form),
        )
    )
    if not forms:
        return Unavailable(exercise="cloze", reason="missing_forms")
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(form) for form in forms) + r")(?!\w)")
    examples = context.sense.fields.get("examples")
    for example in examples if isinstance(examples, list) else ():
        if not isinstance(example, str):
            continue
        sentence = normalize_answer(example)
        match = pattern.search(sentence)
        if match is None:
            continue
        return GeneratedExercise(
            prompt=ExercisePrompt(text=pattern.sub("____", sentence), input="text"),
            private=AnswerSpec(answer=match.group(), accepted_forms=context.forms),
        )
    return Unavailable(exercise="cloze", reason="missing_example")


def register(target: ExerciseRegistry) -> None:
    target.register(ExercisePlugin("cloze", "recall", generate, grade_answer))
