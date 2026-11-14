"""Internal recognition content, never serialized as a public attempt."""

from typing import Any

from app.domain.exercises import ExerciseContext, ExerciseModel


def definition(fields: dict[str, Any]) -> str:
    value = fields.get("definition")
    if isinstance(value, str) and value.strip():
        return value.strip()
    gloss = fields.get("gloss")
    if isinstance(gloss, dict):
        for language in ("zh", "zh-CN", "en"):
            value = gloss.get(language)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


class RelationQuestion(ExerciseModel):
    text: str
    answer: ExerciseContext
    excluded_words: tuple[str, ...] = ()
