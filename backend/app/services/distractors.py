"""Safe recognition choices; no fabricated or provider-generated alternatives."""

import math
import random
import unicodedata

from surrealdb import AsyncSurrealConnection

from app.db import distractors as repository
from app.domain.distractors import ChoiceLabel, DistractorPool, DistractorRecord
from app.domain.exercises import Choice, DistractorCandidates, ExerciseContext, Unavailable


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def frequency_band(value: float | None) -> int | None:
    return math.floor(value) if value is not None and math.isfinite(value) and value > 0 else None


def select_choices(
    pool: DistractorPool,
    *,
    label: ChoiceLabel = "word",
    count: int = 4,
    rng: random.Random | None = None,
) -> DistractorCandidates | Unavailable:
    if not 2 <= count <= 4:
        raise ValueError("Choice count must be between two and four")
    randomizer = rng if rng is not None else random.Random()
    exercise = "def2word" if label == "word" else "word2def"

    def text(record: DistractorRecord) -> str:
        return record.word if label == "word" else record.definition

    answer = text(pool.answer).strip()
    if not answer:
        return Unavailable(exercise=exercise, reason="missing_answer_label")
    forbidden_ids = {pool.answer.sense_id, *(item.sense_id for item in pool.synonyms)}
    seen_ids = set(forbidden_ids)
    seen = {_key(answer), *(_key(text(item)) for item in pool.synonyms)}
    ranked = sorted(pool.candidates, key=lambda item: (item.tier, item.sense_id))
    choices = [Choice(id=pool.answer.sense_id, label=answer)]
    for candidate in ranked:
        if candidate.sense_id in seen_ids or not 0 <= candidate.tier <= 3:
            continue
        if label == "definition" and _key(candidate.word) == _key(pool.answer.word):
            continue
        if candidate.tier == 3:
            band = frequency_band(pool.answer.freq_zipf)
            if (
                not pool.answer.pos
                or candidate.pos != pool.answer.pos
                or band is None
                or frequency_band(candidate.freq_zipf) != band
            ):
                continue
        value = text(candidate).strip()
        key = _key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        seen_ids.add(candidate.sense_id)
        choices.append(Choice(id=candidate.sense_id, label=value))
        if len(choices) == count:
            break
    if len(choices) < 2:
        return Unavailable(exercise=exercise, reason="insufficient_safe_distractors")
    randomizer.shuffle(choices)
    return DistractorCandidates(choices=tuple(choices), answer_choice_id=pool.answer.sense_id)


async def choices(
    db: AsyncSurrealConnection,
    context: ExerciseContext,
    *,
    label: ChoiceLabel = "word",
    count: int = 4,
    rng: random.Random | None = None,
) -> DistractorCandidates | Unavailable:
    """Capture DB/label in a closure to implement the registry's DistractorProvider."""
    pool = await repository.candidate_pool(db, context)
    if pool is None:
        return Unavailable(
            exercise="def2word" if label == "word" else "word2def",
            reason="distractor_pool_unavailable",
        )
    return select_choices(pool, label=label, count=count, rng=rng)
