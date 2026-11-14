from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "done", "failed"]


class JobRejected(Exception):
    """A handler's terminal, public-safe failure code, never provider exception text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class JobCreate(BaseModel):
    type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict, repr=False)
    owner: str | None = None
    run_after: datetime | None = None


class JobRead(BaseModel):
    id: str
    type: str
    status: JobStatus
    attempts: int
    run_after: datetime
    error: str | None = None


class Job(JobRead):
    payload: dict[str, Any] = Field(repr=False)
    owner: str | None = None
