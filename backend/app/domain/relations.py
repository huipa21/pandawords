"""Personal semantic relations, without caller-controlled ownership or provenance."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type RelationType = Literal[
    "synonym", "antonym", "hypernym", "hyponym", "confusable", "collocation", "default"
]


class RelationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str = Field(min_length=1, max_length=16384)
    end: str = Field(min_length=1, max_length=16384)
    type: RelationType


class RelationRead(BaseModel):
    id: str
    start: str
    end: str
    start_label: str
    end_label: str
    type: RelationType
    source: str
    readonly: bool


class RelationResult(BaseModel):
    relation: RelationRead
    created: bool
