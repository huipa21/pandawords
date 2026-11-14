from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "user"]


class UserPreferences(BaseModel):
    theme: Literal["system", "light", "dark"] = "system"
    locale: str = "zh-CN"
    accent: Literal["US", "UK"] = "US"
    review_images_enabled: bool = True
    review_audio_enabled: bool = True
    desired_retention: float = Field(default=0.9, gt=0, lt=1, allow_inf_nan=False)


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


class UserRead(BaseModel):
    id: str
    username: str
    role: Role
    disabled: bool
    must_change_password: bool
    source_lang: str
    target_lang: str
    prefs: UserPreferences


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024, repr=False)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024, repr=False)
    new_password: str = Field(min_length=10, max_length=1024, repr=False)


class AuthRead(BaseModel):
    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"
    user: UserRead


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
