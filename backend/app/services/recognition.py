"""Offline recognition plugins; opaque choices and answer keys are attempt-local."""

import random
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from surrealdb import AsyncSurrealConnection

from app.db import recognition as repository
from app.domain.distractors import ChoiceLabel
from app.domain.exercises import (
    AnswerSpec,
    Choice,
    DistractorCandidates,
    ExerciseContext,
    ExercisePrompt,
    GeneratedExercise,
    Unavailable,
)
from app.domain.recognition import RelationQuestion, definition
from app.services import distractors
from app.services.exercise_answers import grade_answer, normalize_answer
from app.services.exercise_registry import ExercisePlugin, ExerciseRegistry


class RecognitionProvider(Protocol):
    async def choices(
        self, context: ExerciseContext, /, *, label: ChoiceLabel = "word"
    ) -> DistractorCandidates | Unavailable: ...

    async def relations(self, context: ExerciseContext, /) -> tuple[RelationQuestion, ...]: ...


@dataclass(frozen=True)
class DatabaseProvider:
    db: AsyncSurrealConnection

    async def choices(
        self, context: ExerciseContext, *, label: ChoiceLabel = "word"
    ) -> DistractorCandidates | Unavailable:
        return await distractors.choices(self.db, context, label=label)

    async def relations(self, context: ExerciseContext) -> tuple[RelationQuestion, ...]:
        return await repository.relation_questions(self.db, context)


def _generate(
    exercise: str,
    text: str,
    candidates: DistractorCandidates | Unavailable,
    excluded_words: tuple[str, ...] = (),
) -> GeneratedExercise | Unavailable:
    if isinstance(candidates, Unavailable):
        return Unavailable(exercise=exercise, reason=candidates.reason)
    forbidden = {normalize_answer(word) for word in excluded_words}
    seen: set[str] = set()
    options: list[Choice] = []
    answer: Choice | None = None
    # Keep the answer first during validation so an equivalent distractor can never replace it.
    ranked = sorted(candidates.choices, key=lambda item: item.id != candidates.answer_choice_id)
    for candidate in ranked:
        correct = candidate.id == candidates.answer_choice_id
        label = candidate.label.strip()
        key = normalize_answer(label)
        if not key or key in seen or (not correct and key in forbidden):
            continue
        seen.add(key)
        option = Choice(id=uuid4().hex, label=label)
        options.append(option)
        if correct:
            answer = option
    if answer is None or not 2 <= len(options) <= 4:
        return Unavailable(exercise=exercise, reason="insufficient_safe_distractors")
    random.SystemRandom().shuffle(options)
    return GeneratedExercise(
        prompt=ExercisePrompt(text=text, input="choice", choices=tuple(options)),
        private=AnswerSpec(choice_id=answer.id, answer=answer.label),
    )


def _word_prompt(context: ExerciseContext) -> str:
    word = str(context.lemma.fields.get("text", "")).strip()
    if not word:
        return ""
    pos = context.lexeme.fields.get("pos")
    parts = [word, f"({pos})"] if pos else [word]
    pronunciations = context.lexeme.fields.get("pron")
    if isinstance(pronunciations, list):
        for item in pronunciations:
            if not isinstance(item, dict):
                continue
            ipa, accent = item.get("ipa"), item.get("accent")
            if isinstance(ipa, str) and ipa.strip():
                parts.append(f"{accent}: {ipa.strip()}" if accent in ("US", "UK") else ipa.strip())
    return " ".join(parts)


def register(target: ExerciseRegistry, provider: RecognitionProvider) -> None:
    async def def2word(context: ExerciseContext) -> GeneratedExercise | Unavailable:
        text = definition(context.sense.fields)
        if not text:
            return Unavailable(exercise="def2word", reason="missing_definition")
        return _generate("def2word", text, await provider.choices(context))

    async def word2def(context: ExerciseContext) -> GeneratedExercise | Unavailable:
        text = _word_prompt(context)
        if not text or not definition(context.sense.fields):
            return Unavailable(exercise="word2def", reason="missing_word_or_definition")
        return _generate("word2def", text, await provider.choices(context, label="definition"))

    async def relation(context: ExerciseContext) -> GeneratedExercise | Unavailable:
        questions = list(await provider.relations(context))
        random.SystemRandom().shuffle(questions)
        for question in questions:
            result = _generate(
                "relation",
                question.text,
                await provider.choices(question.answer),
                question.excluded_words,
            )
            if isinstance(result, GeneratedExercise):
                return result
        return Unavailable(exercise="relation", reason="missing_relation_or_safe_choices")

    for name, generator in (
        ("def2word", def2word),
        ("word2def", word2def),
        ("relation", relation),
    ):
        target.register(ExercisePlugin(name, "recognition", generator, grade_answer))
