"""Internal scheduling contracts; grades are supplied only by the exercise framework."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from fsrs import Card, Rating, State
from pydantic import BaseModel, ConfigDict, Field, field_validator

ExerciseKind = Literal["recognition", "recall"]


class SrsPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    desired_retention: float = Field(default=0.9, gt=0, lt=1, allow_inf_nan=False)


class SrsPreferencesUpdate(SrsPreferences):
    desired_retention: float = Field(gt=0, lt=1, allow_inf_nan=False)


class CardState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    card_id: int
    state: State
    step: int | None = None
    stability: float | None = None
    difficulty: float | None = None
    due: datetime
    last_review: datetime | None = None

    @field_validator("due", "last_review")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Card timestamps must be timezone aware")
        return value.astimezone(UTC)

    @classmethod
    def from_card(cls, card: Card) -> CardState:
        return cls.model_validate(card.to_dict())

    def to_card(self) -> Card:
        return Card(
            card_id=self.card_id,
            state=self.state,
            step=self.step,
            stability=self.stability,
            difficulty=self.difficulty,
            due=self.due,
            last_review=self.last_review,
        )


class MemoryRead(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    sense_id: str
    introduced: bool
    card: CardState

    @property
    def version(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class FrameworkGrade(BaseModel):
    """Server-only input, never used as an HTTP request model."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    exercise: str = Field(min_length=1, max_length=128)
    kind: ExerciseKind
    correct: bool
    gave_up: bool = False
    hint_used: bool = False
    duration_ms: int = Field(strict=True, ge=0)

    @field_validator("duration_ms")
    @classmethod
    def cap_duration(cls, value: int) -> int:
        return min(value, 60000)


class GradedReview(BaseModel):
    """Persist this immutable server-side value in the attempt, not in client state."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    attempt_id: str = Field(min_length=1, max_length=256)
    project_id: str
    sense_id: str
    expected_version: str
    grade: FrameworkGrade
    auto_rating: Rating


class ReviewReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)
    attempt_id: str
    project_id: str
    memory: MemoryRead
    auto_rating: Rating
    rating: Rating
    correct: bool
    at: datetime
    is_introduction: bool


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
