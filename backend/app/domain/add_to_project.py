"""Selected candidate identities, membership result and versioned worker payloads."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.dictionary import MaterializedDictionary
from app.domain.dictionary_keys import DictionaryKey, lemma_key, sense_key
from app.domain.jobs import JobRead


class AddToProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    lemma_key: DictionaryKey = Field(min_length=2, max_length=2)
    selected_senses: list[DictionaryKey] = Field(max_length=1000)

    @field_validator("lemma_key")
    @classmethod
    def validate_lemma(cls, key: DictionaryKey) -> DictionaryKey:
        if not all(isinstance(part, str) for part in key):
            raise ValueError("Expected a candidate lemma key")
        if key != lemma_key(str(key[0]), str(key[1])) or key[0] != "en":
            raise ValueError("Expected a canonical English candidate lemma key")
        return key

    @field_validator("selected_senses")
    @classmethod
    def validate_senses(cls, keys: list[DictionaryKey]) -> list[DictionaryKey]:
        for key in keys:
            if (
                len(key) != 5
                or not all(isinstance(key[index], str) for index in (0, 1, 2, 4))
                or type(key[3]) is not int
                or key
                != sense_key(
                    str(key[0]),
                    str(key[1]),
                    str(key[2]),
                    key[3],
                    source_sense_id=str(key[4]),
                )
            ):
                raise ValueError("Expected canonical candidate sense keys")
        return keys


class AddToProjectRead(MaterializedDictionary):
    project_id: str
    membership_ids: list[str]
    jobs: list[JobRead]


class DictionaryJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    lemma_key: DictionaryKey
    lemma_id: str
    lexeme_id: str


class EnrichJobPayload(DictionaryJobPayload):
    sense_id: str


class AudioJobPayload(DictionaryJobPayload):
    accent: Literal["US", "UK"]
