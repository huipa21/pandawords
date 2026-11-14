import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid
from app.db import exercise_test_support as probe
from app.db.auth import _atomic
from app.db.exercise_context import selected_context
from app.services import exercise_attempts, recognition
from app.services.exercise_registry import ExerciseRegistry, registry
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.api.test_exercise_attempts import assert_no_key
from tests.conftest import UserFactory
from tests.exercise_support import Clock
from tests.integration.srs_support import create_study
from tests.integration.test_distractor_graph import entry, semantic, tag_pair

pytestmark = pytest.mark.integration
URL = "/api/exercise-attempts"


@pytest.mark.parametrize("exercise", ["def2word", "word2def", "relation"])
@pytest.mark.parametrize("submission", ["correct", "wrong", "giveup"])
async def test_real_recognition_attempt_lifecycle_and_owner_isolation(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
    exercise: str,
    submission: str,
) -> None:
    study = await create_study(db, make_user, lexicon_reader)
    source = await _atomic(
        db,
        lambda txn: selected_context(
            db,
            study.user.id,
            decode_rid(study.project.id, "project"),
            decode_rid(study.sense_id, "sense"),
            txn,
        ),
    )
    answer, safe = [await entry(db, study.user.id, frequency=0) for _ in range(2)]
    await tag_pair(db, source, answer, "concept")
    await tag_pair(db, answer, safe, "concept")
    await semantic(db, source, answer, "antonym")
    target = ExerciseRegistry()
    recognition.register(target, recognition.DatabaseProvider(db))
    monkeypatch.setattr(registry, "_plugins", {exercise: target.get(exercise)})
    clock = Clock()
    monkeypatch.setattr(exercise_attempts, "_now", clock.now)
    headers = bearer(await login(client, study.user.username))
    opened_response = await client.post(
        URL,
        headers=headers,
        json={"project_id": study.project.id, "sense_id": study.sense_id},
    )
    assert opened_response.status_code == 201, opened_response.text
    opened = opened_response.json()
    assert opened["exercise"] == exercise and opened["kind"] == "recognition"
    assert_no_key(opened)
    assert 2 <= len(opened["prompt"]["choices"]) <= 4
    assert all(len(item["id"]) == 32 for item in opened["prompt"]["choices"])
    path = f"{URL}/{opened['id']}"
    assert_no_key((await client.get(path, headers=headers)).json())
    stored = await probe.saved(db, study.user.id, opened["id"])
    correct_id = stored.generated.private.choice_id
    assert correct_id is not None
    assert correct_id in {item["id"] for item in opened["prompt"]["choices"]}

    bob = await make_user()
    bob_headers = bearer(await login(client, bob.username))
    assert (await client.get(path, headers=bob_headers)).status_code == 404
    for action, foreign_body in (
        ("hint", None),
        ("answer", {"answer": correct_id, "duration_ms": 0}),
        ("giveup", {"duration_ms": 0}),
        ("confirm", {"rating": 4}),
    ):
        response = await client.post(path + "/" + action, headers=bob_headers, json=foreign_body)
        assert response.status_code == 404
    foreign_create = await client.post(
        URL,
        headers=bob_headers,
        json={"project_id": study.project.id, "sense_id": study.sense_id},
    )
    assert foreign_create.status_code == 404
    clock.advance(1)
    body: dict[str, str | int] = {"duration_ms": 1000}
    action = "giveup" if submission == "giveup" else "answer"
    if submission != "giveup":
        body["answer"] = (
            correct_id
            if submission == "correct"
            else next(
                item["id"] for item in opened["prompt"]["choices"] if item["id"] != correct_id
            )
        )
    graded = await client.post(path + "/" + action, headers=headers, json=body)
    assert graded.status_code == 200, graded.text
    assert graded.json()["feedback"]["correct"] == (submission == "correct")
    assert graded.json()["auto_rating"] == (3 if submission == "correct" else 1)
    confirmed = await client.post(path + "/confirm", headers=headers, json={"rating": 4})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["receipt"]["rating"] == 4
    logs = await probe.logs(db, study.user.id)
    assert len(logs) == 1 and logs[0]["exercise"] == exercise
    assert logs[0]["auto_rating"] == (3 if submission == "correct" else 1)
    assert logs[0]["rating"] == 4
    assert await probe.logs(db, bob.id) == []
