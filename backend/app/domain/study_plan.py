"""Study-plan and dashboard response contracts."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.domain.projects import ProjectPlan
from app.domain.srs import MemoryRead


class CompletedCounts(BaseModel):
    new: int = 0
    reviews: int = 0


class ForecastDay(BaseModel):
    date: date
    due: int


class ExamPacing(BaseModel):
    remaining_new: int
    days_left: int
    suggested_daily_new: int
    capacity: int
    buffer_capacity: int
    impossible: bool
    buffer_at_risk: bool


class StudyQueueItem(BaseModel):
    kind: Literal["review", "new"]
    memory: MemoryRead
    retrievability: float | None = None

    @computed_field
    @property
    def memory_version(self) -> str:
        return self.memory.version


class StudyPlanRead(BaseModel):
    project_id: str
    as_of: datetime
    plan: ProjectPlan
    due: int
    new: int
    today: CompletedCounts
    remaining_new_allowance: int
    remaining_review_allowance: int | None
    queue: list[StudyQueueItem]
    queue_total: int
    offset: int
    limit: int
    exam: ExamPacing | None
    forecast: list[ForecastDay]


class SenseOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sense_ids: list[str] = Field(max_length=10_000)

    @field_validator("sense_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Sense IDs must be unique")
        return value


class SenseOrderRead(BaseModel):
    project_id: str
    sense_ids: list[str]


class ProjectForecast(BaseModel):
    project_id: str
    name: str
    due: int
    new: int
    today: CompletedCounts
    forecast: list[ForecastDay]
    exam: ExamPacing | None


class DashboardRead(BaseModel):
    as_of: datetime
    due_today: int
    new_today: int
    today: CompletedCounts
    retention_30_days: float | None
    streak: int
    forecast: list[ForecastDay]
    projects: list[ProjectForecast]
