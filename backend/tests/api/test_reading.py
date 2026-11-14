import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.api.dependencies import get_lexicon_reader
from app.core.record_ids import decode_rid
from app.db.project_schema_test_support import put_override
from app.domain.identity import user_key
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_reading_effective_project_selection_and_isolation(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    app.dependency_overrides[get_lexicon_reader] = lambda: lexicon_reader
    alice, bob = await make_user(), await make_user()
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    project = (await client.post("/api/projects", headers=ah, json={"name": "Reading"})).json()
    foreign = (await client.post("/api/projects", headers=bh, json={"name": "Private"})).json()
    passage = (
        await client.post(
            "/api/content/ingest",
            headers=ah,
            json={"text": "🙂 Cat. bank xyzunknown!", "source": "Original"},
        )
    ).json()
    url = f"/api/content/passage/{passage['passage']['id']}/reading"
    query = {"project_id": project["id"]}
    empty = await client.get(url, headers=ah, params=query)
    assert empty.status_code == 200, empty.text
    assert empty.json()["project_senses"] == []
    assert [part["order"] for part in empty.json()["sentences"]] == [0, 1]
    assert empty.json()["passage"]["source"] == "Original"
    assert empty.json()["sentences"][1]["occurrences"][0]["status"] == "ambiguous"
    candidates = (
        await client.post("/api/dictionary/candidates", headers=ah, json={"text": "cat"})
    ).json()["candidates"]
    candidate = candidates[0]
    sense = candidate["lexemes"][0]["senses"][0]
    added = await client.post(
        f"/api/projects/{project['id']}/dictionary",
        headers=ah,
        json={"lemma_key": candidate["lemma"]["id"], "selected_senses": [sense["id"]]},
    )
    assert added.status_code == 200, added.text
    selection = added.json()
    sense_id = selection["selected_sense_ids"][0]
    await put_override(
        db,
        RecordID("user", user_key(alice.id)),
        decode_rid(sense_id, "sense"),
        {"definition": "My effective cat", "gloss": {"zh": "我的猫"}},
    )
    selected = (await client.get(url, headers=ah, params=query)).json()
    assert [item["id"] for item in selected["project_senses"]] == [sense_id]
    assert selected["project_senses"][0]["fields"]["definition"] == "My effective cat"
    assert selected["project_senses"][0]["fields"]["gloss"]["zh"] == "我的猫"
    for table, target in (
        ("sense", sense_id),
        ("lexeme", selection["lexeme_ids"][0]),
        ("lemma", selection["lemma_id"]),
    ):
        visibility = f"/api/projects/{project['id']}/tree/{table}/{target}/visibility"
        assert (
            await client.patch(visibility, headers=ah, json={"hidden": True})
        ).status_code == 200
        assert (await client.get(url, headers=ah, params=query)).json()["project_senses"] == []
        assert (
            await client.patch(visibility, headers=ah, json={"hidden": False})
        ).status_code == 200
    assert (await client.get(url, headers=ah)).json()["project_senses"] == []
    assert (await client.get(url, headers=bh)).status_code == 404
    assert (await client.get(url, headers=bh, params=query)).status_code == 404
    assert (
        await client.get(url, headers=ah, params={"project_id": foreign["id"]})
    ).status_code == 404
    sentence = passage["sentences"][0]["sentence"]["id"]
    assert (
        await client.get(f"/api/content/sentence/{sentence}/occurrences", headers=bh)
    ).status_code == 404
