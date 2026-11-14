from datetime import UTC, datetime, timedelta

import pytest
from fsrs import Card, Rating, Scheduler
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.srs import CardState, FrameworkGrade, SrsPreferences
from app.services.srs_rating import auto_rating


@pytest.mark.parametrize("rating", list(Rating))
def test_complete_card_roundtrip_after_each_rating(rating: Rating) -> None:
    now = datetime(2026, 11, 14, tzinfo=UTC)
    scheduler = Scheduler()
    original = Card(due=now)
    assert CardState.from_card(original).to_card().to_dict() == original.to_dict()
    for index in range(3):
        original, _ = scheduler.review_card(
            original,
            rating,
            review_datetime=now + timedelta(days=index),
        )
        persisted = CardState.from_card(original)
        restored = CardState.model_validate_json(persisted.model_dump_json()).to_card()
        assert restored.to_dict() == original.to_dict()


@pytest.mark.parametrize(
    ("kind", "correct", "hint", "gave_up", "duration", "expected"),
    [
        ("recall", False, False, False, 1, Rating.Again),
        ("recognition", True, False, True, 1, Rating.Again),
        ("recall", True, True, False, 1, Rating.Hard),
        ("recognition", True, True, False, 1, Rating.Hard),
        ("recall", True, False, False, 4999, Rating.Easy),
        ("recall", True, False, False, 5000, Rating.Good),
        ("recall", True, False, False, 20000, Rating.Good),
        ("recall", True, False, False, 20001, Rating.Hard),
        ("recognition", True, False, False, 2999, Rating.Good),
        ("recognition", True, False, False, 3000, Rating.Good),
        ("recognition", True, False, False, 12000, Rating.Good),
        ("recognition", True, False, False, 12001, Rating.Hard),
    ],
)
def test_defaults_and_strict_boundaries(
    kind: str,
    correct: bool,
    hint: bool,
    gave_up: bool,
    duration: int,
    expected: Rating,
) -> None:
    grade = FrameworkGrade.model_validate(
        {
            "exercise": "test",
            "kind": kind,
            "correct": correct,
            "hint_used": hint,
            "gave_up": gave_up,
            "duration_ms": duration,
        }
    )
    assert auto_rating(grade, [], Settings()) == expected


@pytest.mark.parametrize(
    ("count", "duration", "expected"),
    [
        (19, 5999, Rating.Good),
        (20, 5999, Rating.Easy),
        (20, 6000, Rating.Good),
        (20, 18000, Rating.Good),
        (20, 18001, Rating.Hard),
    ],
)
def test_median_thresholds(count: int, duration: int, expected: Rating) -> None:
    grade = FrameworkGrade(exercise="cloze", kind="recall", correct=True, duration_ms=duration)
    assert auto_rating(grade, [10000] * count, Settings()) == expected


def test_cap_invalid_durations_and_configurable_defaults() -> None:
    grade = FrameworkGrade(exercise="cloze", kind="recall", correct=True, duration_ms=99999)
    assert grade.duration_ms == 60000
    assert auto_rating(grade, [], Settings(srs_recall_slow_ms=60000)) == Rating.Good
    for invalid in [-1, True, 1.5, "10"]:
        with pytest.raises(ValidationError):
            FrameworkGrade.model_validate(
                {
                    "exercise": "cloze",
                    "kind": "recall",
                    "correct": True,
                    "duration_ms": invalid,
                }
            )
    for invalid in [0, 1, -0.1, float("nan"), float("inf")]:
        with pytest.raises(ValidationError):
            SrsPreferences(desired_retention=invalid)
