"""Offline cloze from owner-private contexts or selected-sense source examples."""

import re
from collections.abc import Awaitable, Callable

from surrealdb import AsyncSurrealConnection

from app.db import exercise_cloze as repository
from app.domain.exercises import (
    AnswerSpec,
    ExerciseContext,
    ExercisePrompt,
    GeneratedExercise,
    Unavailable,
)
from app.services.cloze_context import mask
from app.services.exercise_answers import grade_answer, normalize_answer
from app.services.exercise_registry import ExercisePlugin, ExerciseRegistry

ContextProvider = Callable[[ExerciseContext], Awaitable[tuple[repository.SentenceContext, ...]]]


async def generate(
    context: ExerciseContext, source: ContextProvider | None = None
) -> GeneratedExercise | Unavailable:
    if source is not None:
        for sentence in await source(context):
            masked = mask(sentence, context.forms)
            if masked is not None:
                text, answer = masked
                return GeneratedExercise(
                    prompt=ExercisePrompt(text=text, input="text"),
                    private=AnswerSpec(answer=answer, accepted_forms=context.forms),
                )
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


def provider(db: AsyncSurrealConnection) -> ContextProvider:
    async def acquire(context: ExerciseContext) -> tuple[repository.SentenceContext, ...]:
        return await repository.sentences(db, context)

    return acquire


def register(target: ExerciseRegistry, source: ContextProvider | None = None) -> None:
    async def create(context: ExerciseContext) -> GeneratedExercise | Unavailable:
        return await generate(context, source)

    target.register(ExercisePlugin("cloze", "recall", create, grade_answer))
