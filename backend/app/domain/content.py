"""Private reading content; offsets are half-open Unicode code-point offsets."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

type ContentKind = Literal["sentence", "passage"]
ContentText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20000)]
ContentLanguage = Annotated[
    str, StringConstraints(strict=True, max_length=35, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
]
ContentSpan = tuple[StrictInt, StrictInt]


class ContentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: ContentText
    lang: ContentLanguage = "en"
    source: Annotated[str, StringConstraints(strict=True, max_length=2000)] = ""
    title: Annotated[str, StringConstraints(strict=True, max_length=300)] = ""
    translation: dict[
        ContentLanguage, Annotated[str, StringConstraints(strict=True, max_length=20000)]
    ] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def meaningful(self) -> Self:
        if not self.text.strip() or "\x00" in self.text:
            raise ValueError("Text must contain visible content and no NUL.")
        if len(re.findall(r"\w+(?:['’-]\w+)*", self.text)) > 2000:
            raise ValueError("Content exceeds 2000 tokens.")
        return self


class ContentRead(ContentCreate):
    id: str
    kind: ContentKind


class ContentCandidate(BaseModel):
    lemma: str
    sense_id: str
    definition: str


class Occurrence(BaseModel):
    text: str
    span: ContentSpan
    candidates: list[ContentCandidate]
    status: Literal["unmatched", "unresolved", "ambiguous", "resolved"]
    sense_id: str | None = None
    edge_id: str | None = None


class SentencePart(BaseModel):
    sentence: ContentRead
    order: int
    span: ContentSpan
    occurrences: list[Occurrence] = Field(default_factory=list)


class PassageRead(BaseModel):
    passage: ContentRead
    sentences: list[SentencePart]
    assistance: str = "not_requested"


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span: ContentSpan
    sense_id: str


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolutions: list[Resolution] = Field(max_length=100)


class AnalysisRead(BaseModel):
    sentence: ContentRead
    occurrences: list[Occurrence]
    assistance: str = "not_requested"
    suggestions: list[Resolution] = Field(default_factory=list)


class PartAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=16384)]
