from typing import Any
from uuid import UUID

import pytest
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid
from app.db.auth import _atomic
from app.db.exercise_context import selected_context
from app.domain.exercises import ExerciseContext
from app.domain.jobs import Job
from app.services import jobs
from app.services.exercise_answers import selected_lexeme_forms
from tests.integration.srs_support import Study

TEXT = "The bus is leaving, so Maya moves quickly on foot to reach the stop."


@pytest.fixture
def settings() -> Settings:
    options: dict[str, Any] = {
        "_env_file": None,
        "deepseek_api_key": "sk-test-secret",
        "llm_max_retries": 0,
        "llm_timeout_seconds": 30,
    }
    return Settings(**options)


async def study_context(db: AsyncSurrealConnection, study: Study) -> ExerciseContext:
    async def operation(txn: UUID) -> ExerciseContext:
        return await selected_context(
            db,
            study.user.id,
            decode_rid(study.project.id, "project"),
            decode_rid(study.sense_id, "sense"),
            txn,
        )

    context = await _atomic(db, operation)
    return context.model_copy(
        update={"forms": selected_lexeme_forms(context.lemma, context.lexeme)}
    )


@pytest.fixture
def scheduled(monkeypatch: pytest.MonkeyPatch) -> list[Job]:
    result: list[Job] = []
    original = jobs.enqueue

    async def enqueue(*args, **kwargs):
        job = await original(*args, **kwargs)
        if job.type == "scenario":
            result.append(job)
        return job

    monkeypatch.setattr(jobs, "enqueue", enqueue)
    return result


async def claim_scenario(db: AsyncSurrealConnection) -> Job:
    for _ in range(20):
        job = await jobs.claim(db)
        assert job is not None
        if job.type == "scenario":
            return job
        await jobs.complete(db, job)
    raise AssertionError("Scenario job was not queued")
