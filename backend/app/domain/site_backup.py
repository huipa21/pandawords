"""Operator site backup (`pandawords.site`) manifest and API models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import AppError

SITE_FORMAT = "pandawords.site"
SITE_VERSION = 1
SITE_ATTRIBUTION = [
    "Wiktionary (CC BY-SA)",
    "Open English WordNet (CC BY 4.0)",
    "ECDICT (MIT)",
]
type SiteBackupTrigger = Literal["manual", "scheduled"]
_SHA256 = r"^[0-9a-f]{64}$"


class SiteBackupFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=1024)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256)


class SiteBackupDatabase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Literal["db.surql"] = "db.surql"
    size: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256)
    surrealdb_version: str | None = None
    tables: dict[str, int]


class SiteBackupManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["pandawords.site"]
    version: Literal[1]
    app_version: str
    created_at: datetime
    trigger: SiteBackupTrigger
    lexicon_version: str | None
    source_lang: str
    target_lang: str
    attribution: list[str]
    database: SiteBackupDatabase
    media: list[SiteBackupFile]


class SiteBackupRead(BaseModel):
    name: str
    created_at: datetime
    size: int
    sha256: str


class SiteBackupStatus(BaseModel):
    running: bool
    last_error: str | None
    backups: list[SiteBackupRead]


class SiteRestoreResult(BaseModel):
    archive_created_at: datetime
    tables: int
    records: int
    media_files: int
    pre_restore_export: str | None


class SiteBackupError(AppError):
    """A backup/restore stage failed; `stage` is safe to show to an operator."""

    def __init__(self, stage: str, message: str, status: int = 500) -> None:
        self.stage = stage
        super().__init__(f"site_backup.{stage}", status, message)


def backup_in_progress() -> SiteBackupError:
    return SiteBackupError("in_progress", "A site backup or restore is already running.", 409)
