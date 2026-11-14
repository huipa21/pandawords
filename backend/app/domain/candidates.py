"""Offline dictionary candidates, retaining structured identities and attribution."""

import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.dictionary_keys import lemma_key
from app.domain.lexicon import (
    LexiconGloss,
    LexiconLemma,
    LexiconLexeme,
    LexiconPronunciation,
    LexiconSense,
    LexiconSource,
)


class CandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = str(lemma_key("en", value)[1])
        if not any(character.isalpha() for character in normalized):
            raise ValueError("Enter a word or phrase")
        if any(unicodedata.category(character).startswith("C") for character in normalized):
            raise ValueError("Input contains unsupported control characters")
        return normalized


class CandidateLexeme(BaseModel):
    lexeme: LexiconLexeme
    senses: list[LexiconSense]
    pronunciations: list[LexiconPronunciation]
    glosses: list[LexiconGloss]


class Candidate(BaseModel):
    lemma: LexiconLemma
    matched_by: list[Literal["exact", "form", "spacy"]]
    lexemes: list[CandidateLexeme]


class CandidateResponse(BaseModel):
    normalized: str
    candidates: list[Candidate]
    sources: list[LexiconSource]
