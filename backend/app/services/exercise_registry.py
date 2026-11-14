"""Generator plugins depend on domain contracts, never on the attempt service."""

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import structlog
from fsrs import State

from app.core.errors import AppError
from app.domain.exercises import (
    AnswerSpec,
    ClozeSource,
    DistractorCandidates,
    ExerciseContext,
    ExerciseFeedback,
    GeneratedExercise,
    ListeningSource,
    ScenarioSource,
    Unavailable,
)
from app.domain.srs import ExerciseKind, MemoryRead


class ExerciseGenerator(Protocol):
    async def __call__(self, context: ExerciseContext) -> GeneratedExercise | Unavailable: ...


class ExerciseGrader(Protocol):
    def __call__(self, private: AnswerSpec, answer: str) -> ExerciseFeedback: ...


class DistractorProvider(Protocol):
    async def __call__(self, context: ExerciseContext) -> DistractorCandidates | Unavailable: ...


class ClozeProvider(Protocol):
    async def __call__(self, context: ExerciseContext) -> ClozeSource | Unavailable: ...


class ListeningProvider(Protocol):
    async def __call__(self, context: ExerciseContext) -> ListeningSource | Unavailable: ...


class ScenarioProvider(Protocol):
    async def __call__(self, context: ExerciseContext) -> ScenarioSource | Unavailable: ...


@dataclass(frozen=True)
class ExercisePlugin:
    exercise: str
    kind: ExerciseKind
    generate: ExerciseGenerator
    grade: ExerciseGrader


@dataclass(frozen=True)
class Selection:
    plugin: ExercisePlugin
    generated: GeneratedExercise
    skipped: tuple[Unavailable, ...]


class ExerciseRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, ExercisePlugin] = {}

    def register(self, plugin: ExercisePlugin) -> None:
        if not plugin.exercise or plugin.exercise in self._plugins:
            raise ValueError("Exercise identity must be nonempty and unique")
        self._plugins[plugin.exercise] = plugin

    def get(self, exercise: str) -> ExercisePlugin:
        if exercise not in self._plugins:
            raise AppError("exercise.unavailable", 409, "Exercise plugin is unavailable.")
        return self._plugins[exercise]

    async def select(
        self,
        context: ExerciseContext,
        memory: MemoryRead,
        *,
        random_value: Callable[[], float] = random.random,
        disabled: frozenset[str] = frozenset(),
    ) -> Selection:
        review = memory.introduced and memory.card.state == State.Review
        eligible: dict[ExerciseKind, list[tuple[ExercisePlugin, GeneratedExercise]]] = {
            "recognition": [],
            "recall": [],
        }
        skipped: list[Unavailable] = []
        for plugin in sorted(self._plugins.values(), key=lambda item: item.exercise):
            if plugin.exercise in disabled:
                skipped.append(Unavailable(exercise=plugin.exercise, reason="preference"))
                continue
            if not review and plugin.kind != "recognition":
                skipped.append(Unavailable(exercise=plugin.exercise, reason="card_state"))
                continue
            result = await plugin.generate(context)
            if isinstance(result, Unavailable):
                skipped.append(Unavailable(exercise=plugin.exercise, reason=result.reason))
            else:
                eligible[plugin.kind].append((plugin, result))
        if not any(eligible.values()):
            reasons = [item.model_dump() for item in skipped]
            structlog.get_logger().info("exercise_no_usable", skipped=reasons)
            raise AppError(
                "exercise.no_usable",
                409,
                "No usable exercise. "
                + "; ".join(f"{item.exercise}: {item.reason}" for item in skipped),
            )
        recognition, recall = eligible["recognition"], eligible["recall"]
        if recognition and recall:
            recall_weight = 2 if (memory.card.stability or 0) >= 7 else 1
            group = recall if random_value() < recall_weight / (recall_weight + 1) else recognition
        else:
            group = recall or recognition
        plugin, generated = group[min(int(random_value() * len(group)), len(group) - 1)]
        return Selection(plugin, generated, tuple(skipped))


registry = ExerciseRegistry()
