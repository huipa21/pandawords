from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

type TagKind = Literal["morph_group", "concept", "domain", "custom"]
type TagTarget = Literal["sense", "morpheme", "tag"]
type TagName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TagName
    kind: TagKind = "custom"


class TagUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TagName | None = None
    kind: TagKind | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> Self:
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Tag fields cannot be null.")
        return self


class TagRead(BaseModel):
    id: str
    name: str
    kind: TagKind
    readonly: bool


class TagAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_table: TagTarget
    target_id: str


class TagListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TagAssignmentRead(BaseModel):
    tag: TagRead
    readonly: bool
