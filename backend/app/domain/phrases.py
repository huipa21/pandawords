"""Containing phrases retain graph identity separately from offline add candidates."""

from pydantic import BaseModel

from app.domain.candidates import Candidate
from app.domain.dictionary import DictionaryEntryRead
from app.domain.lexicon import LexiconSource


class ContainingPhraseRead(BaseModel):
    entry: DictionaryEntryRead
    candidate: Candidate | None = None


class ContainingPhrasesRead(BaseModel):
    items: list[ContainingPhraseRead]
    sources: list[LexiconSource]
    offset: int
    limit: int
    has_more: bool
