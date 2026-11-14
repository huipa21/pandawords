"""Offline plugins exercise the framework before concrete exercise tasks are registered."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.exercises import (
    AnswerSpec,
    Choice,
    ExerciseContext,
    ExercisePrompt,
    GeneratedExercise,
    Unavailable,
)
from app.domain.srs import ExerciseKind
from app.services.exercise_answers import grade_answer
from app.services.exercise_registry import ExercisePlugin, ExerciseRegistry


@dataclass
class FakeGenerator:
    exercise: str
    kind: ExerciseKind
    unavailable: str | None = None

    async def __call__(self, context: ExerciseContext) -> GeneratedExercise | Unavailable:
        if self.unavailable is not None:
            return Unavailable(exercise=self.exercise, reason=self.unavailable)
        recognition = self.kind == "recognition"
        return GeneratedExercise(
            prompt=ExercisePrompt(
                text="Move quickly on foot",
                input="choice" if recognition else "text",
                choices=(Choice(id="a", label="run"), Choice(id="b", label="walk"))
                if recognition
                else (),
            ),
            private=AnswerSpec(
                answer="run",
                accepted_forms=context.forms,
                choice_id="a" if recognition else None,
                hint="Starts with r",
            ),
        )


def plugins(*generators: FakeGenerator) -> ExerciseRegistry:
    result = ExerciseRegistry()
    for generator in generators:
        result.register(ExercisePlugin(generator.exercise, generator.kind, generator, grade_answer))
    return result


@dataclass
class Clock:
    at: datetime = datetime(2026, 11, 14, 12, 30, tzinfo=UTC)

    def now(self) -> datetime:
        return self.at

    def advance(self, seconds: int) -> None:
        self.at += timedelta(seconds=seconds)
