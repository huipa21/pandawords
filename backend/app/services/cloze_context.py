"""Mask original code-point spans before applying answer normalization."""

import re
import unicodedata

from app.db.exercise_cloze import SentenceContext
from app.services.exercise_answers import normalize_answer


def mask(source: SentenceContext, forms: tuple[str, ...]) -> tuple[str, str] | None:
    accepted = {normalize_answer(form) for form in forms} - {""}
    if not accepted or not source.spans:
        return None
    text = source.text
    spans = sorted(set(source.spans))
    for index, (start, end) in enumerate(spans):
        if (
            not 0 <= start < end <= len(text)
            or normalize_answer(text[start:end]) not in accepted
            or (index > 0 and start < spans[index - 1][1])
        ):
            return None

    # Keep a code-point map through NFKC/case folding (which can change length).
    chunks: list[tuple[int, int]] = []
    for index, char in enumerate(text):
        if chunks and unicodedata.category(char).startswith("M"):
            chunks[-1] = (chunks[-1][0], index + 1)
        else:
            chunks.append((index, index + 1))
    normalized = ""
    offsets: list[tuple[int, int]] = []
    for start, end in chunks:
        value = " " if text[start:end].isspace() else normalize_answer(text[start:end])
        if value == " " and normalized.endswith(" "):
            offsets[-1] = (offsets[-1][0], end)
            continue
        normalized += value
        offsets.extend([(start, end)] * len(value))
    pattern = re.compile(
        r"(?<!\w)(?:"
        + "|".join(re.escape(form) for form in sorted(accepted, key=lambda x: (-len(x), x)))
        + r")(?!\w)"
    )
    occurrences = []
    for match in pattern.finditer(normalized):
        start, end = match.span()
        if (start and offsets[start - 1] == offsets[start]) or (
            end < len(offsets) and offsets[end - 1] == offsets[end]
        ):
            continue
        occurrences.append((offsets[start][0], offsets[end - 1][1]))
    if not set(spans) <= set(occurrences):
        return None
    answer = text[spans[0][0] : spans[0][1]]
    for start, end in reversed(occurrences):
        text = text[:start] + "____" + text[end:]
    return text, answer
