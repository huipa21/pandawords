import base64
import binascii
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_AVATAR_BYTES = 256 * 1024
MAX_AVATAR_LENGTH = 4 * ((MAX_AVATAR_BYTES + 2) // 3) + len("data:image/jpeg;base64,")
LOCAL_PART = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def decode_avatar(value: str) -> tuple[bytes, str]:
    match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]*={0,2})", value)
    if match is None:
        raise ValueError("Avatar must be a PNG, JPEG or WebP base64 data URL")
    try:
        content = base64.b64decode(match[2], validate=True)
    except ValueError, binascii.Error:
        raise ValueError("Malformed avatar base64") from None
    if not content or len(content) > MAX_AVATAR_BYTES:
        raise ValueError("Avatar must contain between 1 byte and 256 KiB")
    return content, match[1]


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(max_length=128)
    email: str = Field(max_length=254)
    avatar: str = Field(max_length=MAX_AVATAR_LENGTH, repr=False)

    @field_validator("full_name", "email", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if not value:
            return value
        local, separator, domain = value.rpartition("@")
        try:
            labels = domain.encode("idna").decode("ascii").split(".")
        except UnicodeError:
            raise ValueError("Invalid email address") from None
        if (
            not separator
            or len(local) > 64
            or LOCAL_PART.fullmatch(local) is None
            or len(labels) < 2
            or any(DOMAIN_LABEL.fullmatch(label) is None for label in labels)
            or labels[-1].isdigit()
        ):
            raise ValueError("Invalid email address")
        return value

    @field_validator("avatar")
    @classmethod
    def valid_avatar(cls, value: str) -> str:
        if value:
            content, mime = decode_avatar(value)
            return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
        return value
