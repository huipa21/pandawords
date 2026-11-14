import re
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from surrealdb import RecordID

MediaKind = Literal["audio", "image"]
MediaSource = Literal["wiktionary", "edge_tts", "pixabay", "upload"]
TARGET_TABLES = frozenset({"lemma", "lexeme", "sense", "morpheme", "tag", "sentence", "passage"})
MIME_EXTENSIONS: dict[MediaKind, dict[str, str]] = {
    "audio": {
        "audio/mpeg": ".mp3",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/mp4": ".m4a",
        "audio/webm": ".webm",
    },
    "image": {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    },
}


def validate_path(value: str) -> str:
    parts = value.split("/")
    if (
        len(value) > 240
        or len(parts) < 2
        or any(
            not re.fullmatch(r"[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*", part)
            or part.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *(f"COM{i}" for i in range(10)),
                *(f"LPT{i}" for i in range(10)),
            }
            for part in parts
        )
    ):
        raise ValueError("Invalid media path")
    return value


class MediaCreate(BaseModel):
    """Trusted worker/service input; target is an SDK record, never query text."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    target: RecordID
    owner: str | None = None
    kind: MediaKind
    mime: str
    source: MediaSource
    attribution: str | None = Field(default=None, max_length=4000)
    accent: Literal["US", "UK"] | None = None

    @field_validator("target")
    @classmethod
    def valid_target(cls, value: RecordID) -> RecordID:
        if value.table_name not in TARGET_TABLES:
            raise ValueError("Invalid media target")
        return value

    @model_validator(mode="after")
    def valid_metadata(self) -> Self:
        if self.mime not in MIME_EXTENSIONS[self.kind]:
            raise ValueError("Invalid media content type")
        if self.kind != "audio" and self.accent is not None:
            raise ValueError("Accent requires audio")
        return self


class Media(MediaCreate):
    id: RecordID
    path: str = Field(repr=False)

    _valid_path = field_validator("path")(validate_path)

    @model_validator(mode="after")
    def valid_stored_path(self) -> Self:
        if (
            self.path.split("/")[0] != self.kind
            or PurePosixPath(self.path).suffix != MIME_EXTENSIONS[self.kind][self.mime]
        ):
            raise ValueError("Media path does not match content type")
        return self


class MediaRead(BaseModel):
    """Safe metadata for internal callers; filesystem paths are deliberately omitted."""

    id: str
    target: str
    kind: MediaKind
    mime: str
    source: MediaSource
    attribution: str | None
    accent: Literal["US", "UK"] | None
