"""Strict timing boundaries and owner/type-specific historical suggestions."""

from collections.abc import Sequence
from statistics import median

from fsrs import Rating

from app.core.config import Settings
from app.domain.srs import FrameworkGrade


def auto_rating(
    grade: FrameworkGrade, prior_correct_ms: Sequence[int], settings: Settings
) -> Rating:
    if not grade.correct or grade.gave_up:
        return Rating.Again
    if grade.hint_used:
        return Rating.Hard
    if len(prior_correct_ms) >= 20:
        middle = median(prior_correct_ms[:100])
        fast, slow = middle * 0.6, middle * 1.8
    elif grade.kind == "recognition":
        fast, slow = settings.srs_recognition_fast_ms, settings.srs_recognition_slow_ms
    else:
        fast, slow = settings.srs_recall_fast_ms, settings.srs_recall_slow_ms
    if grade.duration_ms > slow:
        return Rating.Hard
    if grade.kind == "recall" and grade.duration_ms < fast:
        return Rating.Easy
    return Rating.Good
