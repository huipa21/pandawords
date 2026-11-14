"""Runtime lexicon records; identities use the shared structured dictionary keys."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.domain.dictionary_keys import DictionaryKey

type RelationType = Literal["synonym", "antonym", "hypernym", "hyponym"]
type RelationDirection = Literal["outgoing", "incoming"]
type Accent = Literal["US", "UK"]


class LexiconRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LexiconLemma(LexiconRecord):
    id: DictionaryKey
    text: str
    lang: str
    kind: Literal["word", "phrase"]
    freq_zipf: float | None
    cefr: str | None
    source: str


class LexiconLexeme(LexiconRecord):
    id: DictionaryKey
    lemma_id: DictionaryKey
    pos: str
    etymology_no: int
    etymology_text: str | None
    source: str


class LexiconSense(LexiconRecord):
    id: DictionaryKey
    lexeme_id: DictionaryKey
    definition: str
    glosses: list[str]
    gloss_zh: str | None
    tags: list[str]
    registers: list[str] = Field(alias="register")
    domain: list[str]
    examples: list[dict[str, JsonValue]]
    rank: int
    common: bool
    source: str
    source_id: str | None
    lexname: str | None


class LexiconPronunciation(LexiconRecord):
    id: str
    lexeme_id: DictionaryKey
    accent: Accent | None
    ipa: str | None
    audio: dict[str, JsonValue]
    tags: list[str]
    source: str


class LexiconForm(LexiconRecord):
    lexeme_id: DictionaryKey
    form: str
    tags: list[str]
    source: str


class LexiconRelation(LexiconRecord):
    source_sense_id: DictionaryKey
    target_sense_id: DictionaryKey
    type: RelationType
    source: str


class LexiconGloss(LexiconRecord):
    lexeme_id: DictionaryKey
    gloss: str
    source: str
    sense_id: DictionaryKey | None


class LexiconTag(LexiconRecord):
    lemma_id: DictionaryKey
    tag: str
    source: str


class LexiconFrequency(LexiconRecord):
    lemma_id: DictionaryKey
    zipf: float | None
    bnc: int | None
    coca: int | None
    source: str


class LexiconAffix(LexiconRecord):
    lexeme_id: DictionaryKey
    position: int
    text: str
    type: Literal["prefix", "root", "suffix", "infix"]
    source: str


class LexiconSource(LexiconRecord):
    name: str
    metadata: dict[str, JsonValue]


class LexiconPhraseComponent(LexiconRecord):
    phrase_id: DictionaryKey
    lexeme_id: DictionaryKey
    position: int = Field(ge=0, lt=32)
    source: str


class LexiconPhraseUsage(LexiconRecord):
    phrase_id: DictionaryKey
    sense_id: DictionaryKey
    source: str
