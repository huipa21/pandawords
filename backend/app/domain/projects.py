from datetime import UTC, datetime
from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Language = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=35)]


class ProjectPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_new: int = Field(default=20, ge=0, le=9_223_372_036_854_775_807, strict=True)
    exam_date: AwareDatetime | None = None
    review_cap: int | None = Field(default=None, ge=0, le=9_223_372_036_854_775_807, strict=True)

    @field_validator("exam_date")
    @classmethod
    def utc_exam_date(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    description: str = Field(default="", max_length=10000)
    target_lang: Language = "en"
    source_lang: Language = "zh"
    plan: ProjectPlan = Field(default_factory=ProjectPlan)


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName | SkipJsonSchema[None] = None
    description: Annotated[str, Field(max_length=10000)] | SkipJsonSchema[None] = None
    target_lang: Language | SkipJsonSchema[None] = None
    source_lang: Language | SkipJsonSchema[None] = None
    plan: ProjectPlan | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def reject_null_changes(self) -> Self:
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Changes cannot be null")
        return self


class ProjectRead(BaseModel):
    id: str
    name: str
    description: str
    target_lang: str
    source_lang: str
    plan: ProjectPlan
    created_at: datetime


class ProjectPage(BaseModel):
    items: list[ProjectRead]
    total: int
    page: int
    page_size: int
