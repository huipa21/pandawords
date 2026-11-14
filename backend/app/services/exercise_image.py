"""Offline exact-sense image recall; no filenames or provider search metadata escape."""

import asyncio
import html
from functools import partial
from pathlib import Path
from urllib.parse import unquote

from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.domain.exercises import (
    AnswerSpec,
    ExerciseContext,
    ExercisePrompt,
    GeneratedExercise,
    Unavailable,
)
from app.domain.images import MAX_BYTES
from app.services import image_validation, images, media
from app.services.exercise_answers import grade_answer, normalize_answer
from app.services.exercise_registry import ExercisePlugin, ExerciseRegistry


def safe_attribution(value: str | None, forms: tuple[str, ...]) -> bool:
    if not value:
        return True
    decoded = value
    for _ in range(3):
        decoded = html.unescape(unquote(decoded))
    normalized = normalize_answer(decoded)
    return not any(normalize_answer(form) in normalized for form in forms if form.strip())


def _validate_file(path: Path, mime: str) -> None:
    with path.open("rb") as stream:
        image_validation.validate(stream.read(MAX_BYTES + 1), mime)


async def generate(
    db: AsyncSurrealConnection, settings: Settings, context: ExerciseContext
) -> GeneratedExercise | Unavailable:
    missing = Unavailable(exercise="image2word", reason="missing_image")
    if not context.forms:
        return missing
    try:
        candidates = await images.list_images(db, context.sense_id, context.owner)
    except AppError, OSError, ValueError:
        return missing
    for candidate in sorted(candidates, key=lambda item: item.id):
        try:
            record = await media._load(db, settings, candidate.id, context.owner)
            if (
                record.owner != context.owner
                or record.kind != "image"
                or encode_rid(record.target, "sense") != context.sense_id
                or (record.source == "pixabay" and not record.attribution)
                or not safe_attribution(record.attribution, context.forms)
            ):
                continue
            path = await asyncio.to_thread(media._file, settings.media_dir, record.path)

            await asyncio.to_thread(_validate_file, path, record.mime)
        except AppError, OSError, ValueError:
            continue
        return GeneratedExercise(
            prompt=ExercisePrompt(
                text="",
                input="text",
                media_id=candidate.id,
                media_attribution=record.attribution,
            ),
            private=AnswerSpec(answer=context.forms[0], accepted_forms=context.forms),
        )
    return missing


def register(target: ExerciseRegistry, db: AsyncSurrealConnection, settings: Settings) -> None:
    target.register(
        ExercisePlugin("image2word", "recall", partial(generate, db, settings), grade_answer)
    )
