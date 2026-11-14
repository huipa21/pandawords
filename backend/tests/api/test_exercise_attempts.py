import asyncio
import json

import pytest
from fsrs import Rating
from httpx import AsyncClient
from surrealdb import AsyncSurrealConnection
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db import exercise_test_support as probe
from app.services import exercise_attempts, srs
from app.services.exercise_registry import registry
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory
from tests.exercise_support import Clock, FakeGenerator, plugins
from tests.integration.srs_support import Study, create_study

pytestmark = pytest.mark.integration
URL = "/api/exercise-attempts"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(exercise_attempts, "_now", clock.now)
    return clock


@pytest.fixture
async def study(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
    clock: Clock,
) -> Study:
    fake = plugins(FakeGenerator("fake_recognition", "recognition"))
    monkeypatch.setattr(registry, "_plugins", fake._plugins)
    return await create_study(db, make_user, lexicon_reader)


async def issue(client: AsyncClient, study: Study) -> tuple[dict[str, str], dict]:
    headers = bearer(await login(client, study.user.username))
    response = await client.post(
        URL,
        headers=headers,
        json={
            "project_id": study.project.id,
            "sense_id": study.sense_id,
        },
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return headers, response.json()


def assert_no_key(value: dict) -> None:
    text = str(value)
    for key in (
        "accepted_forms",
        "choice_id",
        "correct",
        "auto_rating",
        "expected_version",
        "review",
        "private",
        "feedback",
        "receipt",
        "restriction",
        "answer",
    ):
        assert f"'{key}':" not in text


async def test_full_lifecycle_concurrent_retries_manual_override(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    study: Study,
    clock: Clock,
) -> None:
    headers, opened = await issue(client, study)
    path = f"{URL}/{opened['id']}"
    assert opened["status"] == "open" and opened["hint"] is None
    assert_no_key(opened)
    assert_no_key((await client.get(path, headers=headers)).json())
    assert (
        await client.post(path + "/confirm", headers=headers, json={"rating": 4})
    ).status_code == 409
    initial = await srs.read_memory(db, study.user.id, study.sense_id)
    assert not initial.introduced and await probe.logs(db, study.user.id) == []
    for _ in range(2):
        hint = await client.post(path + "/hint", headers=headers)
        assert hint.status_code == 200
        assert hint.json()["hint_used"] and hint.json()["hint"] == "Starts with r"
        assert_no_key(hint.json())
    clock.advance(10)
    body = {"answer": "a", "duration_ms": 9000}
    results = await asyncio.gather(
        *[client.post(path + "/answer", headers=headers, json=body) for _ in range(3)]
    )
    assert all(result.status_code == 200 for result in results), [r.text for r in results]
    graded = results[0].json()
    assert all(result.json() == graded for result in results)
    assert graded["status"] == "graded" and graded["feedback"] == {"correct": True, "answer": "run"}
    assert graded["auto_rating"] == 2 and graded["duration_ms"] == 9000
    assert graded["server_elapsed_ms"] == 10000
    stored = await probe.saved(db, study.user.id, opened["id"])
    assert stored.expected_version == initial.version and stored.review is not None
    assert stored.review.grade.hint_used
    assert await srs.read_memory(db, study.user.id, study.sense_id) == initial
    assert await probe.logs(db, study.user.id) == []
    assert (await client.post(path + "/hint", headers=headers)).status_code == 409
    assert (
        await client.post(path + "/answer", headers=headers, json={**body, "answer": "b"})
    ).status_code == 409
    assert (
        await client.post(path + "/giveup", headers=headers, json={"duration_ms": 9000})
    ).status_code == 409
    results = await asyncio.gather(
        *[client.post(path + "/confirm", headers=headers, json={"rating": 4}) for _ in range(3)]
    )
    assert all(result.status_code == 200 for result in results), [r.text for r in results]
    confirmed = results[0].json()
    assert all(result.json() == confirmed for result in results)
    receipt = confirmed["receipt"]
    assert receipt["rating"] == 4 and receipt["auto_rating"] == 2 and receipt["correct"]
    logs = await probe.logs(db, study.user.id)
    assert len(logs) == 1 and logs[0]["rating"] == 4 and logs[0]["auto_rating"] == 2
    assert logs[0]["duration_ms"] == 9000 and logs[0]["hint_used"]
    assert (await client.get(path, headers=headers)).json() == confirmed
    assert (await client.post(path + "/answer", headers=headers, json=body)).json() == confirmed
    assert (
        await client.post(path + "/confirm", headers=headers, json={"rating": 1})
    ).status_code == 409
    clock.advance(2000)
    assert (
        await client.post(path + "/confirm", headers=headers, json={"rating": 4})
    ).json() == confirmed


@pytest.mark.parametrize("answer,expected", [("a", True), ("b", False), (None, False)])
async def test_correct_wrong_giveup(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    study: Study,
    clock: Clock,
    answer,
    expected,
) -> None:
    headers, opened = await issue(client, study)
    clock.advance(8)
    path = f"{URL}/{opened['id']}"
    body = {"duration_ms": 8000}
    if answer is not None:
        body["answer"] = answer
    suffix = "/giveup" if answer is None else "/answer"
    response = await client.post(path + suffix, headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["feedback"]["correct"] == expected
    assert response.json()["auto_rating"] == (3 if expected else 1)
    assert (await client.post(path + suffix, headers=headers, json=body)).json() == response.json()
    await client.post(path + "/confirm", headers=headers, json={"rating": 4})
    logs = await probe.logs(db, study.user.id)
    assert len(logs) == 1 and logs[0]["correct"] == expected


@pytest.mark.parametrize(
    "client_ms,seconds,expected",
    [
        (3000, 5, 3000),
        (900000, 5, 5000),
        (900000, 75, 60000),
        (1000, 0, 0),
    ],
)
async def test_server_elapsed_bounds_duration(
    client: AsyncClient,
    study: Study,
    clock: Clock,
    client_ms,
    seconds,
    expected,
) -> None:
    headers, opened = await issue(client, study)
    clock.advance(seconds)
    response = await client.post(
        f"{URL}/{opened['id']}/answer",
        headers=headers,
        json={"answer": "a", "duration_ms": client_ms},
    )
    assert response.status_code == 200, response.text
    assert response.json()["duration_ms"] == expected
    assert response.json()["server_elapsed_ms"] == seconds * 1000


@pytest.mark.parametrize("suffix", ["/answer", "/giveup"])
@pytest.mark.parametrize("duration", [-1, 1.5, "2", True, None, float("inf"), float("nan")])
async def test_invalid_duration_does_not_grade(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    study: Study,
    suffix: str,
    duration,
) -> None:
    headers, opened = await issue(client, study)
    body = {"duration_ms": duration}
    if suffix == "/answer":
        body["answer"] = "a"
    response = await client.post(
        f"{URL}/{opened['id']}{suffix}",
        headers={**headers, "Content-Type": "application/json"},
        content=json.dumps(body),
    )
    assert response.status_code == 422
    assert (await probe.saved(db, study.user.id, opened["id"])).status == "open"
    assert await probe.logs(db, study.user.id) == []


async def test_all_attempt_routes_reject_other_owner_and_unauthenticated(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    study: Study,
) -> None:
    headers, opened = await issue(client, study)
    other = await make_user()
    foreign = bearer(await login(client, other.username))
    response = await client.post(
        URL,
        headers=foreign,
        json={
            "project_id": study.project.id,
            "sense_id": study.sense_id,
        },
    )
    assert response.status_code == 404
    path = f"{URL}/{opened['id']}"
    for auth, status in ((foreign, 404), ({}, 401)):
        assert (await client.get(path, headers=auth)).status_code == status
        for suffix, body in (
            ("/hint", None),
            ("/answer", {"answer": "a", "duration_ms": 10}),
            ("/giveup", {"duration_ms": 10}),
            ("/confirm", {"rating": 4}),
        ):
            response = await client.post(path + suffix, headers=auth, json=body)
            assert response.status_code == status, response.text
    assert not (await probe.saved(db, study.user.id, opened["id"])).hint_used
    assert await probe.logs(db, study.user.id) == []
    await client.post(path + "/answer", headers=headers, json={"answer": "a", "duration_ms": 10})
    assert (
        await client.post(path + "/confirm", headers=foreign, json={"rating": 4})
    ).status_code == 404
    assert await probe.logs(db, study.user.id) == []


async def test_registry_empty_is_explicit_and_does_not_review(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    study: Study,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "_plugins", {})
    headers = bearer(await login(client, study.user.username))
    response = await client.post(
        URL,
        headers=headers,
        json={
            "project_id": study.project.id,
            "sense_id": study.sense_id,
        },
    )
    assert response.status_code == 409 and response.json()["code"] == "exercise.no_usable"
    assert await probe.logs(db, study.user.id) == []


async def test_attempt_persists_without_generator_or_application_instance(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    test_settings: Settings,
    study: Study,
    monkeypatch: pytest.MonkeyPatch,
    clock: Clock,
) -> None:
    headers, opened = await issue(client, study)
    path = f"{URL}/{opened['id']}"
    clock.advance(5)
    await client.post(path + "/answer", headers=headers, json={"answer": "a", "duration_ms": 5000})
    monkeypatch.setattr(registry, "_plugins", {})
    async with AsyncWsSurrealConnection(test_settings.surreal_url) as independent:
        await independent.signin(
            {"username": test_settings.surreal_user, "password": test_settings.surreal_pass}
        )
        await independent.use(test_settings.surreal_namespace, test_settings.surreal_database)
        read = await exercise_attempts.read_attempt(independent, study.user.id, opened["id"])
        assert read.status == "graded"
        confirmed = await exercise_attempts.confirm(
            independent, study.user.id, opened["id"], Rating.Good
        )
        assert confirmed.status == "confirmed"
