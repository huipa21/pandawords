"""Effective dictionary views and the result of a shared materialization."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

type DictionaryTable = Literal["lemma", "lexeme", "sense", "morpheme", "tag", "sentence", "passage"]
type DictionaryRelation = Literal[
    "has_lexeme",
    "has_sense",
    "composed_of",
    "derives_to",
    "relates_to",
    "member_of",
    "contains",
    "used_in",
    "part_of",
]


class DictionaryRecordRead(BaseModel):
    """Transport-safe record; fields are schema fields, never ownership or identity."""

    model_config = ConfigDict(extra="forbid")

    id: str
    table: DictionaryTable
    owner: str | None
    fields: dict[str, JsonValue]


class DictionaryEdgeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    table: DictionaryRelation
    start: str
    end: str
    owner: str | None
    fields: dict[str, JsonValue]


class DictionaryLexemeRead(BaseModel):
    lexeme: DictionaryRecordRead
    senses: list[DictionaryRecordRead]


class DictionaryEntryRead(BaseModel):
    lemma: DictionaryRecordRead
    lexemes: list[DictionaryLexemeRead]


class MaterializedDictionary(BaseModel):
    lemma_id: str
    lexeme_ids: list[str]
    selected_sense_ids: list[str] = Field(default_factory=list)
