from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "user"]


class UserPreferences(BaseModel):
    theme: Literal["system", "light", "dark"] = "system"
    locale: str = "zh-CN"
    accent: Literal["US", "UK"] = "US"


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=10, repr=False)
    role: Role = "user"
    disabled: bool = False
    must_change_password: bool = True
    source_lang: str = "zh"
    target_lang: str = "en"
    prefs: UserPreferences = Field(default_factory=UserPreferences)


class User(BaseModel):
    id: str
    username: str
    password_hash: str = Field(repr=False)
    role: Role
    disabled: bool
    must_change_password: bool
    source_lang: str
    target_lang: str
    prefs: UserPreferences


@dataclass(frozen=True)
class AccessClaims:
    sub: str
    role: Role
    exp: int
    iat: int


@dataclass(frozen=True)
class AuthTokens:
    user: User
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    token_type: Literal["bearer"] = "bearer"
