from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.db import exercise_test_support as probe
from app.db.dictionary_schema_test_support import visible
from app.db.study_plan_test_support import schedule
from app.services import srs
from app.services.lexicon import LexiconReader
from tests.api.test_exercise_attempts import URL, assert_no_key, issue
from tests.api.test_recall_attempts import examples
from tests.api.test_recall_attempts import recall_plugins as recall_plugins
from tests.api.test_recall_attempts import study as study
from tests.conftest import UserFactory
from tests.integration.srs_support import Study, create_study
from tests.integration.test_context_cloze import db as db
from tests.integration.test_context_cloze import sentence
from tests.integration.test_context_cloze import test_settings as test_settings

pytestmark = pytest.mark.integration


async def test_private_context_never_crosses_prompt_attempt_or_cache_and_confirms_once(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    study: Study,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    shared_cache = await visible(db, "llm_cache", None)
    bob = await create_study(db, make_user, lexicon_reader)
    bob_card = await srs.read_memory(db, bob.user.id, bob.sense_id)
    await schedule(db, bob.user.id, bob_card, datetime.now(UTC))
    await examples(db, study, [])
    await examples(db, bob, ["Bob can run."])
    row, edge = await sentence(db, study, "😀 ALICE-PRIVATE: running then ran.")
    before = await srs.read_memory(db, study.user.id, study.sense_id)
    headers, opened = await issue(client, study)
    assert opened["exercise"] == "cloze"
    assert opened["prompt"]["text"] == "😀 ALICE-PRIVATE: ____ then ____."
    assert_no_key(opened)
    assert row not in str(opened) and edge not in str(opened)
    bob_headers, other = await issue(client, bob)
    assert other["prompt"]["text"] == "bob can ____."
    assert "ALICE-PRIVATE" not in str(other)
    path = f"{URL}/{opened['id']}"
    for suffix in ("", "/hint", "/answer", "/confirm"):
        if not suffix:
            response = await client.get(path, headers=bob_headers)
        else:
            payload = {
                "/hint": {},
                "/answer": {"answer": "run", "duration_ms": 0},
                "/confirm": {"rating": 3},
            }[suffix]
            response = await client.post(path + suffix, headers=bob_headers, json=payload)
        assert response.status_code == 404
        assert "ALICE-PRIVATE" not in response.text
    response = await client.get(path, headers=headers)
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["prompt"] == opened["prompt"]
    response = await client.post(
        path + "/answer", headers=headers, json={"answer": " RAN ", "duration_ms": 0}
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["feedback"] == {"correct": True, "answer": "running"}
    assert await probe.logs(db, study.user.id) == []
    assert (await srs.read_memory(db, study.user.id, study.sense_id)).version == before.version
    receipt = await client.post(path + "/confirm", headers=headers, json={"rating": 3})
    retry = await client.post(path + "/confirm", headers=headers, json={"rating": 3})
    assert receipt.status_code == retry.status_code == 200
    assert receipt.json() == retry.json()
    logs = await probe.logs(db, study.user.id)
    assert len(logs) == 1
    assert await probe.logs(db, bob.user.id) == []
    assert (await srs.read_memory(db, study.user.id, study.sense_id)).version != before.version
    _, again = await issue(client, bob)
    assert "ALICE-PRIVATE" not in str(again)
    assert await visible(db, "llm_cache", None) == shared_cache
