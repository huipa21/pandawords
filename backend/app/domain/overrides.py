"""Editable presentation fields; identity, provenance and record pointers are immutable."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

from app.domain.dictionary import DictionaryTable

type Text = Annotated[StrictStr, Field(max_length=10_000)]
type Language = Annotated[str, Field(pattern=r"^[a-zA-Z]{2,8}(-[a-zA-Z0-9]{1,8})*$")]
type Rank = Annotated[int, Field(strict=True, ge=0, le=9_223_372_036_854_775_807)]


class Form(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form: Text
    tags: list[Text] = Field(default_factory=list, max_length=100)


class Pronunciation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accent: Literal["US", "UK"]
    ipa: Text


class OverrideFields(BaseModel):
    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)

    text: Text | None = None
    cefr: Text | None = None
    exam_tags: list[Text] | None = Field(default=None, max_length=100)
    etymology_text: Text | None = None
    forms: list[Form] | None = Field(default=None, max_length=100)
    pron: list[Pronunciation] | None = Field(default=None, max_length=100)
    definition: Text | None = None
    gloss: dict[Language, Text] | None = None
    register_: list[Text] | None = Field(default=None, alias="register", max_length=100)
    domain: list[Text] | None = Field(default=None, max_length=100)
    examples: list[Text] | None = Field(default=None, max_length=100)
    rank: Rank | None = None
    common: StrictBool | None = None
    meaning: Text | None = None
    name: Text | None = None
    translation: dict[Language, Text] | None = None
    title: Text | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> Self:
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Omit unchanged fields; use reset to remove overrides.")
        return self


EDITABLE_FIELDS: dict[DictionaryTable, frozenset[str]] = {
    "lemma": frozenset({"text", "cefr", "exam_tags"}),
    "lexeme": frozenset({"etymology_text", "forms", "pron"}),
    "sense": frozenset({"definition", "gloss", "register", "domain", "examples", "rank", "common"}),
    "morpheme": frozenset({"text", "meaning"}),
    "tag": frozenset({"name"}),
    "sentence": frozenset({"text", "translation"}),
    "passage": frozenset({"title", "text"}),
}


class OverrideUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: OverrideFields


class OverrideRead(BaseModel):
    target_table: DictionaryTable
    target_id: str
    fields: OverrideFields
    updated_at: datetime
