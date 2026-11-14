"""Internal, effective dictionary candidates for recognition choices."""

from typing import Literal

from app.domain.exercises import ExerciseModel

type ChoiceLabel = Literal["word", "definition"]


class DistractorRecord(ExerciseModel):
    sense_id: str
    word: str
    definition: str
    pos: str | None = None
    freq_zipf: float | None = None
    tier: int


class DistractorPool(ExerciseModel):
    answer: DistractorRecord
    candidates: tuple[DistractorRecord, ...]
    synonyms: tuple[DistractorRecord, ...] = ()
