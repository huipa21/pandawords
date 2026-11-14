from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.overrides import Language, Rank, Text


class CustomSenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)

    definition: Annotated[Text, StringConstraints(strip_whitespace=True, min_length=1)]
    gloss: dict[Language, Text] = Field(default_factory=dict)
    register_: list[Text] = Field(default_factory=list, alias="register", max_length=100)
    domain: list[Text] = Field(default_factory=list, max_length=100)
    examples: list[Text] = Field(default_factory=list, max_length=100)
    rank: Rank = 0
    common: bool = Field(default=False, strict=True)
