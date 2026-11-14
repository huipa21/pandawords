from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.srs_test_support import remove_memory, seed_history
from app.db.study_plan_test_support import schedule
from app.services import srs, study_plan
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory
from tests.integration.srs_support import create_study
from tests.integration.study_plan_support import three_senses

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


@pytest.fixture
def test_settings(job_settings: Settings) -> Settings:
    return job_settings


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def test_due_order_forecasts_retention_streak_and_legacy_reconcile(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study, ids = await three_senses(db, make_user, lexicon_reader)
    memories = [await srs.read_memory(db, study.user.id, key) for key in ids]
    await remove_memory(db, study.user.id, memories[2])
    legacy = await study_plan.read_plan(db, study.user.id, study.project.id, now=NOW)
    assert legacy.new == 3 and len(legacy.queue) == 3
    assert not (await srs.read_memory(db, study.user.id, ids[2])).introduced
    await schedule(
        db,
        study.user.id,
        memories[0],
        NOW - timedelta(days=2),
        stability=100,
        last_review=NOW - timedelta(days=10),
    )
    await schedule(
        db,
        study.user.id,
        memories[1],
        NOW - timedelta(hours=1),
        stability=1,
        last_review=NOW - timedelta(days=10),
    )
    await schedule(db, study.user.id, memories[2], NOW + timedelta(days=6), last_review=NOW)
    plan = await study_plan.read_plan(db, study.user.id, study.project.id, now=NOW)
    assert [item.memory.sense_id for item in plan.queue] == [ids[1], ids[0]]
    assert [day.due for day in plan.forecast] == [2, 0, 0, 0, 0, 0, 1]
    for days, correct in [(0, True), (1, True), (2, False), (29, False), (30, False)]:
        await seed_history(
            db,
            study.user.id,
            memories[0],
            study.project.id,
            "cloze",
            [10000],
            correct=correct,
            at=NOW - timedelta(days=days),
        )
    other = await create_study(db, make_user, lexicon_reader)
    await seed_history(
        db,
        other.user.id,
        await srs.read_memory(db, other.user.id, other.sense_id),
        other.project.id,
        "cloze",
        [10000],
        correct=False,
        at=NOW,
    )
    dashboard = await study_plan.read_dashboard(db, study.user.id, now=NOW)
    assert dashboard.retention_30_days == 0.5 and dashboard.streak == 3
    assert dashboard.due_today == 2 and dashboard.forecast == plan.forecast
    assert (
        await study_plan.read_dashboard(db, study.user.id, now=NOW + timedelta(days=1))
    ).streak == 3
    assert (
        await study_plan.read_dashboard(db, study.user.id, now=NOW + timedelta(days=2))
    ).streak == 0


async def test_complete_plan_update_zero_limits_and_exam_response(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    headers = bearer(await login(client, study.user.username))
    url = f"/api/projects/{study.project.id}"
    updated = await client.patch(
        url,
        headers=headers,
        json={
            "plan": {
                "daily_new": 0,
                "review_cap": 0,
                "exam_date": "2026-11-16T00:00:00+08:00",
            }
        },
    )
    assert updated.status_code == 200
    plan = await study_plan.read_plan(db, study.user.id, study.project.id, now=NOW)
    assert plan.new == 1 and plan.queue == [] and plan.exam is not None
    assert plan.exam.days_left == 2 and plan.exam.capacity == 0 and plan.exam.impossible
    assert plan.exam.suggested_daily_new == 0 and plan.exam.buffer_at_risk
    assert plan.plan.exam_date == datetime(2026, 11, 15, 16, tzinfo=UTC)
    restored = await client.patch(url, headers=headers, json={"plan": {"daily_new": 1}})
    assert restored.json()["plan"] == {"daily_new": 1, "review_cap": None, "exam_date": None}
    response = await client.get(f"{url}/study-plan", headers=headers)
    assert response.json()["queue_total"] == 1 and response.json()["exam"] is None
