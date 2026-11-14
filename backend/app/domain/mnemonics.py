from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MnemonicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    target_table: Literal["lemma", "lexeme", "sense"]
    target_id: str


class MnemonicJob(MnemonicRequest):
    key: str = Field(pattern=r"^[0-9a-f]{64}$")


class MnemonicText(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    text: str = Field(min_length=1, max_length=2000)


class MnemonicSuggestion(BaseModel):
    status: Literal["pending", "ready", "unavailable"]
    job_id: str | None = None
    text: str | None = None
    reason: str | None = None
