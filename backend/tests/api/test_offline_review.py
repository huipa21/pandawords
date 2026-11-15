import asyncio
from datetime import datetime

import pytest
from httpx import AsyncClient
from surrealdb import AsyncSurrealConnection

from app.db import exercise_test_support as probe
from app.domain.add_to_project import AddToProjectCreate
from app.domain.dictionary_keys import sense_key
from app.domain.projects import ProjectCreate
from app.services import exercise_attempts, offline_review, projects, srs
from app.services.add_to_project import add_to_project
from app.services.exercise_registry import registry
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.api.test_exercise_attempts import assert_no_key
from tests.conftest import UserFactory
from tests.exercise_support import Clock, FakeGenerator, plugins

pytestmark = pytest.mark.integration
URL = "/api/exercise-attempts"
SENSES = ("run-move", "run-flow", "run-operate")


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(exercise_attempts, "_now", clock.now)
    return clock


@pytest.fixture(autouse=True)
def fake_registry(monkeypatch: pytest.MonkeyPatch, clock: Clock) -> None:
    fake = plugins(FakeGenerator("fake_recognition", "recognition"))
    monkeypatch.setattr(registry, "_plugins", fake._plugins)
    monkeypatch.setattr("app.api.exercise_attempts.build_registry", lambda *_args: registry)


async def learner(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    reader: LexiconReader,
) -> tuple[str, str, dict[str, str]]:
    user = await make_user()
    project = await projects.create_project(db, user.id, ProjectCreate(name="Offline"))
    data = AddToProjectCreate(
        lemma_key=["en", "run"],
        selected_senses=[sense_key("en", "run", "verb", source_sense_id=s) for s in SENSES],
    )
    await add_to_project(db, reader, user.id, project.id, data)
    return user.id, project.id, bearer(await login(client, user.username))


async def prefetch(
    client: AsyncClient, headers: dict[str, str], project: str, limit: int
) -> list[dict]:
    response = await client.post(
        URL + "/offline", headers=headers, json={"project_id": project, "limit": limit}
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["lease_seconds"] == 86400 and body["active_limit"] == 20
    return body["attempts"]


def lease(attempt: dict) -> float:
    issued = datetime.fromisoformat(attempt["issued_at"])
    return (datetime.fromisoformat(attempt["expires_at"]) - issued).total_seconds()


async def test_prefetch_is_bounded_and_never_extends_leases(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, project, headers = await learner(client, db, make_user, lexicon_reader)
    first = await prefetch(client, headers, project, 2)
    assert len(first) == 2 and len({a["sense_id"] for a in first}) == 2
    for attempt in first:
        assert attempt["status"] == "open" and lease(attempt) == 86400
        assert_no_key(attempt)
    clock.advance(3600)
    second = await prefetch(client, headers, project, 3)
    assert second[:2] == first and len(second) == 3
    assert len({a["sense_id"] for a in second}) == 3
    assert await prefetch(client, headers, project, 3) == second
    assert await prefetch(client, headers, project, 1) == second[:1]
    invalid = await client.post(URL + "/offline", headers=headers, json={"project_id": project, "limit": 21})
    assert invalid.status_code == 422

    monkeypatch.setattr(offline_review, "OFFLINE_ACTIVE_LIMIT", 1)
    _, capped, other = await learner(client, db, make_user, lexicon_reader)
    assert len(await prefetch(client, other, capped, 3)) == 1
    assert len(await prefetch(client, other, capped, 3)) == 1


async def test_reordered_duplicate_sync_creates_exactly_one_receipt_each(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    clock: Clock,
) -> None:
    owner, project, headers = await learner(client, db, make_user, lexicon_reader)
    first, second = await prefetch(client, headers, project, 2)
    clock.advance(3 * 3600)
    receipts = {}
    for attempt, key in ((second, "k" * 16 + "second"), (first, "k" * 16 + "first")):
        path = f"{URL}/{attempt['id']}"
        body = {"answer": "a", "duration_ms": 4000, "client_key": key}
        graded = await asyncio.gather(
            *[client.post(path + "/answer", headers=headers, json=body) for _ in range(3)]
        )
        assert all(r.status_code == 200 for r in graded), [r.text for r in graded]
        assert len({r.text for r in graded}) == 1 and graded[0].json()["status"] == "graded"
        conflict = await client.post(
            path + "/answer", headers=headers, json={**body, "client_key": "x" * 16}
        )
        assert conflict.status_code == 409
        rating = {"rating": graded[0].json()["auto_rating"]}
        confirmed = await asyncio.gather(
            *[client.post(path + "/confirm", headers=headers, json=rating) for _ in range(3)]
        )
        assert all(r.status_code == 200 for r in confirmed), [r.text for r in confirmed]
        receipts[attempt["id"]] = {r.json()["receipt"]["at"] for r in confirmed}
        retried = await client.post(path + "/answer", headers=headers, json=body)
        assert retried.json()["status"] == "confirmed"
    assert all(len(values) == 1 for values in receipts.values())
    logs = await probe.logs(db, owner)
    assert sorted(log["attempt_id"] for log in logs) == sorted(receipts)


async def test_expired_or_stale_lease_is_rejected_without_fsrs_change(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    clock: Clock,
) -> None:
    owner, project, headers = await learner(client, db, make_user, lexicon_reader)
    expiring, stale = await prefetch(client, headers, project, 2)
    before = await srs.read_memory(db, owner, expiring["sense_id"])
    clock.advance(600)
    online = await client.post(
        URL, headers=headers, json={"project_id": project, "sense_id": stale["sense_id"]}
    )
    path = f"{URL}/{online.json()['id']}"
    await client.post(path + "/answer", headers=headers, json={"answer": "a", "duration_ms": 10})
    assert (await client.post(path + "/confirm", headers=headers, json={"rating": 3})).is_success
    body = {"answer": "a", "duration_ms": 10, "client_key": "s" * 16}
    response = await client.post(f"{URL}/{stale['id']}/answer", headers=headers, json=body)
    assert response.status_code == 409
    assert stale["id"] not in {a["id"] for a in await prefetch(client, headers, project, 3)}

    clock.advance(86400)
    response = await client.post(f"{URL}/{expiring['id']}/answer", headers=headers, json=body)
    assert response.status_code == 410 and response.json()["code"] == "exercise.expired"
    after = await srs.read_memory(db, owner, expiring["sense_id"])
    assert after.version == before.version and not after.introduced
    assert [log["attempt_id"] for log in await probe.logs(db, owner)] == [online.json()["id"]]
    renewed = await prefetch(client, headers, project, 3)
    assert expiring["id"] not in {a["id"] for a in renewed}


async def test_offline_prefetch_and_sync_are_owner_isolated(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    owner, project, headers = await learner(client, db, make_user, lexicon_reader)
    _, foreign_project, foreign = await learner(client, db, make_user, lexicon_reader)
    mine = await prefetch(client, headers, project, 2)
    denied = await client.post(
        URL + "/offline", headers=foreign, json={"project_id": project, "limit": 2}
    )
    assert denied.status_code == 404
    unauthenticated = await client.post(URL + "/offline", json={"project_id": project})
    assert unauthenticated.status_code == 401
    theirs = await prefetch(client, foreign, foreign_project, 3)
    assert not {a["id"] for a in theirs} & {a["id"] for a in mine}
    path = f"{URL}/{mine[0]['id']}/answer"
    body = {"answer": "a", "duration_ms": 10, "client_key": "f" * 16}
    assert (await client.post(path, headers=foreign, json=body)).status_code == 404
    assert await prefetch(client, headers, project, 2) == mine
    assert await probe.logs(db, owner) == []
