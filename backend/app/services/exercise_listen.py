"""Listening uses already-stored, authorized audio; it never acquires recordings."""

from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError
from app.db import exercise_audio
from app.domain.exercises import (
    AnswerSpec,
    ExerciseContext,
    ExercisePrompt,
    GeneratedExercise,
    ListeningSource,
    Unavailable,
)
from app.domain.lexicon import Accent
from app.services import media
from app.services.exercise_answers import grade_answer, normalize_answer
from app.services.exercise_registry import ExercisePlugin, ExerciseRegistry, ListeningProvider


def provider(db: AsyncSurrealConnection, settings: Settings, accent: Accent) -> ListeningProvider:
    async def source(context: ExerciseContext) -> ListeningSource | Unavailable:
        pronunciations = context.lexeme.fields.get("pron")
        for pronunciation in pronunciations if isinstance(pronunciations, list) else ():
            if not isinstance(pronunciation, dict) or pronunciation.get("accent") != accent:
                continue
            rid = pronunciation.get("audio")
            if not isinstance(rid, str):
                continue
            try:
                recording = await media.read(db, settings, rid, context.owner)
            except AppError as exc:
                if exc.status != 404:
                    raise
                continue
            if (
                recording.kind != "audio"
                or recording.accent != accent
                or recording.target != context.lexeme.id
            ):
                continue
            spelling = await exercise_audio.headword(db, context)
            if spelling and normalize_answer(spelling) in context.forms:
                return ListeningSource(media_id=recording.id, represented_form=spelling)
        return Unavailable(exercise="listen", reason="missing_audio")

    return source


def register(target: ExerciseRegistry, source: ListeningProvider) -> None:
    async def generate(context: ExerciseContext) -> GeneratedExercise | Unavailable:
        if not context.forms:
            return Unavailable(exercise="listen", reason="missing_forms")
        result = await source(context)
        if isinstance(result, Unavailable):
            return result
        if normalize_answer(result.represented_form) not in context.forms:
            return Unavailable(exercise="listen", reason="invalid_audio_form")
        return GeneratedExercise(
            prompt=ExercisePrompt(text="", input="text", media_id=result.media_id),
            private=AnswerSpec(answer=result.represented_form, restriction="audio_form"),
        )

    target.register(ExercisePlugin("listen", "recall", generate, grade_answer))
