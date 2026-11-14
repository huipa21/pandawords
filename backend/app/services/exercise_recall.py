"""Request-bound bootstrap; concrete plugins keep their own registration entrypoints."""

from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.domain.lexicon import Accent
from app.services import exercise_cloze, exercise_listen, recognition
from app.services.exercise_registry import ExerciseRegistry, registry


def build_registry(
    db: AsyncSurrealConnection, settings: Settings, accent: Accent
) -> ExerciseRegistry:
    target = ExerciseRegistry()
    for plugin in registry._plugins.values():
        target.register(plugin)
    exercise_cloze.register(target)
    exercise_listen.register(target, exercise_listen.provider(db, settings, accent))
    recognition.register(target, recognition.DatabaseProvider(db))
    return target
