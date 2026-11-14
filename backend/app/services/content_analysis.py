"""Bounded offline segmentation and lexicon occurrence matching."""

import asyncio
import re
import unicodedata

from surrealdb import RecordID

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.domain.content import ContentCandidate, ContentSpan, Occurrence
from app.services.candidates import lemmatize_word
from app.services.lexicon import LexiconReader

_BOUNDARY = re.compile(r"""[。！？]+["'”’」』)]*\s*|[.!?]+["'”’」』)]*(?:\s+|$)|\n+""")


def tokens(text: str) -> list[tuple[str, ContentSpan]]:
    result = []
    index = 0
    while index < len(text):
        if not text[index].isalpha():
            index += 1
            continue
        start = index
        index += 1
        while index < len(text):
            char = text[index]
            if char.isalpha() or unicodedata.category(char).startswith("M"):
                index += 1
            elif char in "'’-" and index + 1 < len(text) and text[index + 1].isalpha():
                index += 1
            else:
                break
        result.append((text[start:index], (start, index)))
    return result


def split(text: str) -> list[tuple[str, ContentSpan]]:
    parts: list[tuple[str, ContentSpan]] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        end = match.end()
        if text[start:end].strip():
            parts.append((text[start:end], (start, end)))
            start = end
    if start < len(text):
        if text[start:].strip() or not parts:
            parts.append((text[start:], (start, len(text))))
        else:
            previous, span = parts[-1]
            parts[-1] = (previous + text[start:], (span[0], len(text)))
    if len(parts) > 200:
        raise AppError("content.too_many_sentences", 422, "At most 200 sentences are allowed.")
    return parts


async def analyze(reader: LexiconReader, text: str, lang: str) -> list[Occurrence]:
    result: list[Occurrence] = []
    cache: dict[str, list[ContentCandidate]] = {}
    for token, span in tokens(text):
        key = token.casefold()
        if key not in cache:
            lemmas = await reader.lookup_form(key, lang=lang)
            direct = await reader.get_lemma(key, lang=lang)
            if direct is not None and all(item.id != direct.id for item in lemmas):
                lemmas.append(direct)
            if not lemmas and lang == "en":
                base = await asyncio.to_thread(lemmatize_word, key)
                if base != key:
                    lemmas = await reader.lookup_form(base, lang=lang)
                    direct = await reader.get_lemma(base, lang=lang)
                    if direct is not None and all(item.id != direct.id for item in lemmas):
                        lemmas.append(direct)
            candidates: dict[str, ContentCandidate] = {}
            if len(lemmas) > 8:
                raise AppError("content.too_many_candidates", 422, "Too many lemma candidates.")
            for lemma in lemmas:
                lexemes = await reader.lexemes(lemma.id)
                if len(lexemes) > 8:
                    raise AppError(
                        "content.too_many_candidates", 422, "Too many lexeme candidates."
                    )
                for lexeme in lexemes:
                    senses = await reader.senses(lexeme.id)
                    if len(senses) > 32:
                        raise AppError(
                            "content.too_many_candidates", 422, "Too many sense candidates."
                        )
                    for sense in senses:
                        sense_id = encode_rid(RecordID("sense", sense.id), "sense")
                        candidates[sense_id] = ContentCandidate(
                            lemma=lemma.text, sense_id=sense_id, definition=sense.definition
                        )
            # Never mistake truncation for an unambiguous match.
            if len(candidates) > 32:
                raise AppError("content.too_many_candidates", 422, "Too many sense candidates.")
            cache[key] = list(candidates.values())
        matches = cache[key]
        result.append(
            Occurrence(
                text=token,
                span=span,
                candidates=matches,
                status="unmatched"
                if not matches
                else "unresolved"
                if len(matches) == 1
                else "ambiguous",
            )
        )
    return result
