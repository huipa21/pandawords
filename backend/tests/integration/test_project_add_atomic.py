import asyncio
from uuid import UUID

import pytest
from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db.dictionary_schema_test_support import visible
from app.db.jobs_test_support import mark_running
from app.db.project_schema_test_support import owned
from app.domain.add_to_project import AddToProjectCreate
from app.domain.dictionary_keys import sense_key
from app.domain.identity import user_key
from app.domain.jobs import Job, JobCreate
from app.domain.projects import ProjectCreate
from app.services import jobs, projects
from app.services.add_to_project import add_to_project
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def test_enqueue_failure_rolls_back_dictionary_memberships_and_prior_jobs(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user()
    owner = RecordID("user", user_key(user.id))
    project = await projects.create_project(db, user.id, ProjectCreate(name="Rollback"))
    lexemes = await lexicon_reader.lexemes(["en", "decision"])
    senses = await lexicon_reader.senses(lexemes[0].id)
    data = AddToProjectCreate(lemma_key=["en", "decision"], selected_senses=[senses[0].id])
    tables = (
        "lemma",
        "lexeme",
        "sense",
        "morpheme",
        "has_sense",
        "composed_of",
        "includes",
        "job",
        "memory",
    )
    before = {table: await visible(db, table, owner) for table in tables}
    original = jobs.enqueue
    calls = 0

    async def failing_enqueue(
        connection: AsyncSurrealConnection,
        job: JobCreate,
        *,
        dedup_key: str | None = None,
        txn_id: UUID | None = None,
    ) -> Job:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("enqueue unavailable")
        return await original(connection, job, dedup_key=dedup_key, txn_id=txn_id)

    with monkeypatch.context() as patch:
        patch.setattr(jobs, "enqueue", failing_enqueue)
        with pytest.raises(RuntimeError, match="enqueue unavailable"):
            await add_to_project(db, lexicon_reader, user.id, project.id, data)
    assert calls == 2
    assert {table: await visible(db, table, owner) for table in tables} == before
    result = await add_to_project(db, lexicon_reader, user.id, project.id, data)
    repeated = await add_to_project(db, lexicon_reader, user.id, project.id, data)
    assert repeated == result
    assert len(await owned(db, "job", owner)) == len(result.jobs)


async def test_concurrent_add_and_terminal_job_reuse(
    db: AsyncWsSurrealConnection, make_user: UserFactory, lexicon_reader: LexiconReader
) -> None:
    user = await make_user()
    owner = RecordID("user", user_key(user.id))
    project = await projects.create_project(db, user.id, ProjectCreate(name="Concurrent"))
    data = AddToProjectCreate(
        lemma_key=["en", "run"],
        selected_senses=[sense_key("en", "run", "verb", source_sense_id="run-move")],
    )
    results = await asyncio.gather(
        *[add_to_project(db, lexicon_reader, user.id, project.id, data) for _ in range(2)]
    )
    assert results[0] == results[1]
    assert len(await owned(db, "includes", owner)) == 2
    assert len(await owned(db, "job", owner)) == len(results[0].jobs)
    # Complete this user's job directly; do not claim unrelated work from the session DB.
    first = results[0].jobs[0]
    stored = Job.model_validate(
        {
            **first.model_dump(),
            "owner": user.id,
            "payload": {},
            "status": "running",
        }
    )
    await mark_running(db, stored)
    await jobs.complete(db, stored)
    repeated = await add_to_project(db, lexicon_reader, user.id, project.id, data)
    assert repeated.jobs[0].id == first.id and repeated.jobs[0].status == "done"
    assert len(await owned(db, "job", owner)) == len(results[0].jobs)
