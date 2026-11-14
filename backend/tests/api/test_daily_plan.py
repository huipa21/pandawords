from datetime import UTC, datetime, timedelta

import pytest
from fsrs import Rating
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid
from app.db.dictionary_schema_test_support import visible
from app.db.project_schema_test_support import owned
from app.db.srs import user_record
from app.db.srs_test_support import change_owner
from app.db.study_plan_test_support import schedule
from app.domain.project_tree import TreeTable
from app.domain.projects import ProjectCreate, ProjectPlan, ProjectUpdate
from app.services import project_tree, projects, srs, study_plan
from app.services.add_to_project import add_to_project
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory
from tests.integration.srs_support import Study, create_study, graded
from tests.integration.study_plan_support import three_senses

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


@pytest.fixture
def test_settings(job_settings: Settings) -> Settings:
    return job_settings


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def test_empty_bounds_auth_and_all_endpoint_owner_isolation(
    client: AsyncClient,
    make_user: UserFactory,
) -> None:
    alice, bob = await make_user(), await make_user()
    a, b = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    project = (await client.post("/api/projects", headers=a, json={"name": "Empty"})).json()
    url = f"/api/projects/{project['id']}/study-plan"
    response = await client.get(url, headers=a)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["queue"] == [] and plan["new"] == plan["due"] == plan["queue_total"] == 0
    assert plan["today"] == {"new": 0, "reviews": 0} and plan["exam"] is None
    assert len(plan["forecast"]) == 7 and all(day["due"] == 0 for day in plan["forecast"])
    assert response.headers["cache-control"] == "no-store"
    assert (await client.put(f"{url}/order", headers=a, json={"sense_ids": []})).status_code == 200
    for foreign in [url, "/api/projects/invalid/study-plan"]:
        assert (await client.get(foreign, headers=b)).status_code == 404
        assert (
            await client.put(
                f"{foreign}/order",
                headers=b,
                json={"sense_ids": []},
            )
        ).status_code == 404
    assert (
        await client.patch(
            f"/api/projects/{project['id']}",
            headers=b,
            json={"plan": {"daily_new": 0}},
        )
    ).status_code == 404
    dashboard = await client.get("/api/dashboard", headers=a)
    assert dashboard.status_code == 200
    assert dashboard.json()["retention_30_days"] is None and dashboard.json()["streak"] == 0
    assert dashboard.headers["cache-control"] == "no-store"
    foreign = await client.get(f"/api/dashboard?owner={alice.id}", headers=b)
    assert foreign.json()["projects"] == [] and foreign.json()["due_today"] == 0
    for endpoint in [url, "/api/dashboard"]:
        assert (await client.get(endpoint)).status_code == 401
    assert (await client.put(f"{url}/order", json={"sense_ids": []})).status_code == 401
    for query in ["limit=0", "limit=501", "offset=-1", "offset=10001"]:
        assert (await client.get(f"{url}?{query}", headers=a)).status_code == 422


async def test_order_persists_hidden_slots_and_queue_reads_do_not_introduce(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study, ids = await three_senses(db, make_user, lexicon_reader)
    headers = bearer(await login(client, study.user.username))
    url = f"/api/projects/{study.project.id}/study-plan"
    initial = (await client.get(url, headers=headers)).json()
    assert [item["memory"]["sense_id"] for item in initial["queue"]] == ids
    before = await owned(db, "includes", user_record(study.user.id))
    await project_tree.set_visibility(db, study.user.id, study.project.id, "sense", ids[1], True)
    response = await client.put(
        f"{url}/order", headers=headers, json={"sense_ids": [ids[2], ids[0]]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["sense_ids"] == [ids[2], ids[1], ids[0]]
    hidden = (await client.get(url, headers=headers)).json()
    assert [item["memory"]["sense_id"] for item in hidden["queue"]] == [ids[2], ids[0]]
    await project_tree.set_visibility(db, study.user.id, study.project.id, "sense", ids[1], False)
    restored = (await client.get(url, headers=headers)).json()
    assert [item["memory"]["sense_id"] for item in restored["queue"]] == [ids[2], ids[1], ids[0]]
    page = (await client.get(f"{url}?limit=1&offset=1", headers=headers)).json()
    assert page["queue_total"] == 3 and page["queue"][0]["memory"]["sense_id"] == ids[1]
    assert all(not item["memory"]["introduced"] for item in restored["queue"])
    for item in restored["queue"]:
        memory = await srs.read_memory(db, study.user.id, item["memory"]["sense_id"])
        assert item["memory_version"] == memory.version
    tree = await project_tree.read_tree(db, study.user.id, study.project.id, 1, 100, False)
    lemma = tree.items[0].lemma.id
    await project_tree.set_visibility(db, study.user.id, study.project.id, "lemma", lemma, True)
    ancestor_order = await client.put(f"{url}/order", headers=headers, json={"sense_ids": []})
    assert ancestor_order.json()["sense_ids"] == [ids[2], ids[1], ids[0]]
    await project_tree.set_visibility(db, study.user.id, study.project.id, "lemma", lemma, False)
    assert [
        item["memory"]["sense_id"]
        for item in (await client.get(url, headers=headers)).json()["queue"]
    ] == [ids[2], ids[1], ids[0]]
    after = await owned(db, "includes", user_record(study.user.id))
    assert {row["id"]: row["added_at"] for row in before} == {
        row["id"]: row["added_at"] for row in after
    }
    for body, status in [
        ({"sense_ids": [ids[0]]}, 409),
        ({"sense_ids": [ids[0], ids[0]]}, 422),
        ({"sense_ids": ids, "owner": study.user.id}, 422),
    ]:
        assert (await client.put(f"{url}/order", headers=headers, json=body)).status_code == status


async def test_hidden_ancestors_content_and_edge_ownership_filter_queue_and_dashboard(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    tree = await project_tree.read_tree(db, study.user.id, study.project.id, 1, 100, False)
    lemma, lexeme = tree.items[0].lemma.id, tree.items[0].lexemes[0].lexeme.id
    targets_to_hide: list[tuple[TreeTable, str]] = [
        ("lemma", lemma),
        ("lexeme", lexeme),
        ("sense", study.sense_id),
    ]
    for table, target in targets_to_hide:
        await project_tree.set_visibility(
            db,
            study.user.id,
            study.project.id,
            table,
            target,
            True,
        )
        assert (await study_plan.read_plan(db, study.user.id, study.project.id)).queue == []
        assert (await study_plan.read_dashboard(db, study.user.id)).new_today == 0
        await project_tree.set_visibility(
            db,
            study.user.id,
            study.project.id,
            table,
            target,
            False,
        )
    foreign = user_record((await make_user()).id)
    user = user_record(study.user.id)
    edges = []
    for table in ["has_lexeme", "has_sense"]:
        rows = await visible(db, table, user)
        edges.append(
            next(
                row["id"]
                for row in rows
                if row["in"]
                == decode_rid(
                    lemma if table == "has_lexeme" else lexeme,
                    "lemma" if table == "has_lexeme" else "lexeme",
                )
                and row["out"]
                == decode_rid(
                    lexeme if table == "has_lexeme" else study.sense_id,
                    "lexeme" if table == "has_lexeme" else "sense",
                )
            )
        )
    targets = [
        (decode_rid(lemma, "lemma"), None),
        (decode_rid(lexeme, "lexeme"), None),
        (decode_rid(study.sense_id, "sense"), None),
        *[(edge, None) for edge in edges],
    ]
    includes = await owned(db, "includes", user)
    targets.append(
        (
            next(
                row["id"]
                for row in includes
                if row["out"]
                == decode_rid(
                    study.sense_id,
                    "sense",
                )
            ),
            user,
        )
    )
    for target, original in targets:
        await change_owner(db, target, original, foreign)
        assert (await study_plan.read_plan(db, study.user.id, study.project.id)).new == 0, target
        assert (await study_plan.read_dashboard(db, study.user.id)).new_today == 0
        await change_owner(db, target, foreign, original)
    assert (await study_plan.read_plan(db, study.user.id, study.project.id)).new == 1


async def test_shared_cards_completed_counts_limits_and_utc_rollover(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    second = await projects.create_project(db, study.user.id, ProjectCreate(name="Second"))
    await add_to_project(db, lexicon_reader, study.user.id, second.id, study.data)
    assert (await study_plan.read_dashboard(db, study.user.id)).new_today == 1
    at = datetime(2026, 11, 14, 23, 58, tzinfo=UTC)
    await projects.update_project(
        db,
        study.user.id,
        study.project.id,
        ProjectUpdate(plan=ProjectPlan(daily_new=1)),
    )
    first = await srs.apply_review(db, study.user.id, await graded(db, study), Rating.Good, now=at)
    second_study = Study(study.user, second, study.sense_id, study.data)
    await srs.apply_review(
        db,
        study.user.id,
        await graded(db, second_study),
        Rating.Good,
        now=at + timedelta(seconds=1),
    )
    memory = await srs.read_memory(db, study.user.id, study.sense_id)
    await schedule(db, study.user.id, memory, at, last_review=at - timedelta(days=10))
    one = await study_plan.read_plan(
        db, study.user.id, study.project.id, now=at + timedelta(minutes=1)
    )
    two = await study_plan.read_plan(db, study.user.id, second.id, now=at + timedelta(minutes=1))
    assert one.today.new == 1 and one.today.reviews == 0 and one.remaining_new_allowance == 0
    assert two.today.new == 0 and two.today.reviews == 1 and two.new == 0
    assert len(one.queue) == len(two.queue) == 1 and two.remaining_review_allowance is None
    assert one.queue[0].memory.id == first.memory.id == two.queue[0].memory.id
    for cap in [0, 1]:
        await projects.update_project(
            db,
            study.user.id,
            second.id,
            ProjectUpdate(plan=ProjectPlan(daily_new=0, review_cap=cap)),
        )
        blocked = await study_plan.read_plan(
            db, study.user.id, second.id, now=at + timedelta(minutes=1)
        )
        assert blocked.queue == [] and blocked.remaining_review_allowance == 0
    rollover = await study_plan.read_plan(
        db, study.user.id, second.id, now=at + timedelta(minutes=2)
    )
    assert rollover.today.reviews == 0 and len(rollover.queue) == 1
    dashboard = await study_plan.read_dashboard(db, study.user.id, now=at + timedelta(minutes=1))
    assert dashboard.due_today == 1 and dashboard.new_today == 0
    assert dashboard.today.new == dashboard.today.reviews == 1
