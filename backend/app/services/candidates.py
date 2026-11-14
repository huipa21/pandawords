"""Resolve input using the offline lexicon and spaCy's deterministic English lookup."""

import asyncio
from functools import lru_cache
from threading import Lock
from typing import Literal

import spacy
from spacy.language import Language

from app.domain.candidates import (
    Candidate,
    CandidateLexeme,
    CandidateRequest,
    CandidateResponse,
)
from app.domain.lexicon import LexiconLemma
from app.services.lexicon import LexiconReader

_pipeline_lock = Lock()


@lru_cache(maxsize=1)
def _pipeline() -> Language:
    pipeline = spacy.blank("en")
    pipeline.add_pipe("lemmatizer", config={"mode": "lookup"})
    pipeline.initialize()
    return pipeline


def lemmatize_word(text: str) -> str:
    # Initialization and inference both stay in the worker, including on the first request.
    with _pipeline_lock:
        document = _pipeline()(text)
        return document[0].lemma_ if len(document) == 1 else text


class CandidateService:
    def __init__(self, reader: LexiconReader) -> None:
        self.reader = reader

    async def resolve(self, request: CandidateRequest) -> CandidateResponse:
        text = request.text
        candidates: dict[tuple[str | int, ...], Candidate] = {}

        def remember(lemma: LexiconLemma, method: Literal["exact", "form", "spacy"]) -> None:
            key = tuple(lemma.id)
            if key not in candidates:
                candidates[key] = Candidate(lemma=lemma, matched_by=[], lexemes=[])
            if method not in candidates[key].matched_by:
                candidates[key].matched_by.append(method)

        exact = await self.reader.get_lemma(text)
        if exact is not None:
            remember(exact, "exact")
        for lemma in await self.reader.lookup_form(text):
            remember(lemma, "form")
        # Phrase matches are atomic; do not turn an unknown phrase into unrelated words.
        if exact is None and " " not in text:
            base = await asyncio.to_thread(lemmatize_word, text)
            if base != text:
                lemma = await self.reader.get_lemma(base)
                if lemma is not None:
                    remember(lemma, "spacy")
                for lemma in await self.reader.lookup_form(base):
                    remember(lemma, "spacy")

        for candidate in candidates.values():
            for lexeme in await self.reader.lexemes(candidate.lemma.id):
                candidate.lexemes.append(
                    CandidateLexeme(
                        lexeme=lexeme,
                        senses=await self.reader.senses(lexeme.id),
                        pronunciations=await self.reader.pronunciations(lexeme.id),
                        glosses=await self.reader.glosses(lexeme.id),
                    )
                )
        return CandidateResponse(
            normalized=text,
            candidates=list(candidates.values()),
            sources=await self.reader.sources() if candidates else [],
        )
