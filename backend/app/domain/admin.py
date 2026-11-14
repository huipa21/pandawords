from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.domain.auth import Role, UserRead


class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=128)
    role: Role = "user"


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disabled: bool | SkipJsonSchema[None] = None
    role: Role | SkipJsonSchema[None] = None
    reset_password: bool = False

    @model_validator(mode="after")
    def reject_null_changes(self) -> Self:
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Changes cannot be null")
        return self


class AdminUserResult(BaseModel):
    user: UserRead
    temporary_password: str | None = Field(default=None, repr=False)


class AdminUserPage(BaseModel):
    items: list[UserRead]
    total: int
    page: int
    page_size: int
