"""Typed bundle entries for the seven dictionary tables (shared or owner-owned rows)."""

from typing import Annotated, Literal

from pydantic import Field

from app.domain.bundle_edges import Entry, Int, Lang, Ref, Scope, Short, Text

type Strings = Annotated[list[Short], Field(max_length=1000)]
type LangMap = Annotated[dict[Lang, Text], Field(max_length=64)]


class _Record(Entry):
    ref: Ref
    owner: Scope


class Frequency(Entry):
    source: Short
    zipf: float | None = None
    bnc: Int | None = None
    coca: Int | None = None


class ExamTagSource(Entry):
    tag: Short
    source: Short


class LemmaRecord(_Record):
    table: Literal["lemma"]
    text: Short
    lang: Lang
    kind: Literal["word", "phrase"]
    freq_zipf: float
    cefr: Short | None = None
    exam_tags: Strings
    source: Short
    frequencies: Annotated[list[Frequency], Field(max_length=64)] | None = None
    exam_tag_sources: Annotated[list[ExamTagSource], Field(max_length=256)] | None = None


class Form(Entry):
    form: Short
    tags: Strings


class Pronunciation(Entry):
    accent: Literal["US", "UK"]
    ipa: Short
    audio: Ref | None = None


class LexemeRecord(_Record):
    table: Literal["lexeme"]
    pos: Short
    etymology_no: Int
    etymology_text: Text | None = None
    forms: Annotated[list[Form], Field(max_length=1000)]
    pron: Annotated[list[Pronunciation], Field(max_length=100)]


class SenseRecord(_Record):
    table: Literal["sense"]
    definition: Text
    gloss: LangMap
    register_: Strings = Field(alias="register")
    domain: Strings
    examples: Annotated[list[Text], Field(max_length=1000)]
    rank: Int
    common: bool
    source: Short


class MorphemeRecord(_Record):
    table: Literal["morpheme"]
    text: Short
    type: Literal["prefix", "root", "suffix", "infix"]
    meaning: Text | None = None
    source: Short | None = None


class TagRecord(_Record):
    table: Literal["tag"]
    kind: Short
    name: Short


class SentenceRecord(_Record):
    table: Literal["sentence"]
    text: Text
    lang: Lang
    translation: LangMap
    source: Short


class PassageRecord(_Record):
    table: Literal["passage"]
    title: Short
    text: Text
    lang: Lang
    source: Short


type DictRecord = Annotated[
    LemmaRecord
    | LexemeRecord
    | SenseRecord
    | MorphemeRecord
    | TagRecord
    | SentenceRecord
    | PassageRecord,
    Field(discriminator="table"),
]

RECORD_MODELS: dict[str, type[_Record]] = {
    "lemma": LemmaRecord,
    "lexeme": LexemeRecord,
    "sense": SenseRecord,
    "morpheme": MorphemeRecord,
    "tag": TagRecord,
    "sentence": SentenceRecord,
    "passage": PassageRecord,
}
