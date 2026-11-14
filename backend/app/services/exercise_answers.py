"""Deterministic English recall matching; no stemming or cross-lexeme form expansion."""

import unicodedata

from app.domain.dictionary import DictionaryRecordRead
from app.domain.exercises import AnswerSpec, ExerciseFeedback

_PUNCTUATION = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "“": '"', "”": '"', "‐": "-", "‑": "-"})


def normalize_answer(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).translate(_PUNCTUATION).casefold().split())


def selected_lexeme_forms(
    lemma: DictionaryRecordRead, lexeme: DictionaryRecordRead
) -> tuple[str, ...]:
    """The headword plus this lexeme's effective forms only, in stable normalized order."""
    values = [lemma.fields.get("text")]
    forms = lexeme.fields.get("forms")
    if isinstance(forms, list):
        values.extend(item.get("form") for item in forms if isinstance(item, dict))
    return tuple(
        sorted(
            {
                normalize_answer(value)
                for value in values
                if isinstance(value, str) and normalize_answer(value)
            }
        )
    )


def grade_answer(private: AnswerSpec, answer: str) -> ExerciseFeedback:
    if private.choice_id is not None:
        correct = answer == private.choice_id
    else:
        accepted = (
            (private.answer,) if private.restriction == "audio_form" else private.accepted_forms
        )
        correct = bool(normalize_answer(answer)) and normalize_answer(answer) in {
            normalize_answer(form) for form in accepted
        }
    return ExerciseFeedback(correct=correct, answer=private.answer)
