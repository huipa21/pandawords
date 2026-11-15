"""Exercise transport contracts. Answer keys and scheduling inputs stay server-side."""

from datetime import datetime
from typing import Annotated, Literal

from fsrs import Rating
from pydantic import BaseModel, ConfigDict, Field

from app.domain.dictionary import DictionaryRecordRead
from app.domain.srs import ExerciseKind, GradedReview, ReviewReceipt


class ExerciseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Choice(ExerciseModel):
    id: str
    label: str


class ExercisePrompt(ExerciseModel):
    text: str
    input: Literal["choice", "text"]
    choices: tuple[Choice, ...] = ()
    media_id: str | None = None
    media_attribution: str | None = None


class AnswerSpec(ExerciseModel):
    """Only selected-lexeme forms, or the single form represented by listening audio."""

    accepted_forms: tuple[str, ...] = ()
    choice_id: str | None = None
    answer: str
    hint: str | None = None
    restriction: Literal["selected_lexeme", "audio_form"] = "selected_lexeme"


class GeneratedExercise(ExerciseModel):
    prompt: ExercisePrompt
    private: AnswerSpec


class Unavailable(ExerciseModel):
    exercise: str
    reason: str


class ExerciseContext(ExerciseModel):
    owner: str
    project_id: str
    sense_id: str
    lemma: DictionaryRecordRead
    lexeme: DictionaryRecordRead
    sense: DictionaryRecordRead
    forms: tuple[str, ...]


class DistractorCandidates(ExerciseModel):
    """Recognition generators consume safe, deduplicated choices, not raw graph records."""

    choices: tuple[Choice, ...]
    answer_choice_id: str


class ClozeSource(ExerciseModel):
    sentence: str
    represented_form: str


class ListeningSource(ExerciseModel):
    media_id: str
    represented_form: str


class ScenarioSource(ExerciseModel):
    scenario: str
    represented_form: str


class ExerciseFeedback(ExerciseModel):
    correct: bool
    answer: str


class AttemptCreate(ExerciseModel):
    project_id: str
    sense_id: str


type ClientKey = Annotated[str, Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


class AttemptAnswer(ExerciseModel):
    answer: str = Field(max_length=4096)
    duration_ms: int = Field(strict=True, ge=0)
    # Stable offline retry identity; retries with the same key replay the same grade.
    client_key: ClientKey | None = None


class AttemptGiveUp(ExerciseModel):
    duration_ms: int = Field(strict=True, ge=0)
    client_key: ClientKey | None = None


class AttemptConfirm(ExerciseModel):
    rating: Rating


class AttemptPublic(ExerciseModel):
    id: str
    project_id: str
    sense_id: str
    exercise: str
    kind: ExerciseKind
    prompt: ExercisePrompt
    issued_at: datetime
    expires_at: datetime
    hint_used: bool
    hint: str | None = None
    skipped: tuple[Unavailable, ...] = ()


class AttemptOpen(AttemptPublic):
    status: Literal["open"]


class AttemptGraded(AttemptPublic):
    status: Literal["graded"]
    feedback: ExerciseFeedback
    auto_rating: Rating
    duration_ms: int
    server_elapsed_ms: int


class AttemptConfirmed(AttemptPublic):
    status: Literal["confirmed"]
    feedback: ExerciseFeedback
    auto_rating: Rating
    duration_ms: int
    server_elapsed_ms: int
    receipt: ReviewReceipt


type AttemptRead = Annotated[
    AttemptOpen | AttemptGraded | AttemptConfirmed, Field(discriminator="status")
]


class OfflinePrefetch(ExerciseModel):
    project_id: str
    limit: int = Field(default=10, strict=True, ge=1, le=20)


class OfflineBatchRead(ExerciseModel):
    """Open prompts under a fixed offline lease; never answer keys or extended leases."""

    project_id: str
    attempts: tuple[AttemptOpen, ...]
    lease_seconds: int
    active_limit: int


class Attempt(ExerciseModel):
    """Persisted internal state, never a router response or request."""

    id: str
    owner: str
    project_id: str
    sense_id: str
    exercise: str
    kind: ExerciseKind
    generated: GeneratedExercise
    expected_version: str
    issued_at: datetime
    expires_at: datetime
    status: Literal["open", "graded", "confirmed"] = "open"
    hint_used: bool = False
    skipped: tuple[Unavailable, ...] = ()
    submission: str | None = None
    server_elapsed_ms: int | None = None
    feedback: ExerciseFeedback | None = None
    review: GradedReview | None = None
    receipt: ReviewReceipt | None = None
