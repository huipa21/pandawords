from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import visible
from app.db.project_schema_test_support import owned, put_override, set_hidden
from app.domain.add_to_project import AudioJobPayload, EnrichJobPayload
from app.domain.dictionary_keys import sense_key
from app.domain.identity import user_key
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
MOVE = sense_key("en", "run", "verb", source_sense_id="run-move")
FLOW = sense_key("en", "run", "verb", source_sense_id="run-flow")


@pytest.fixture
def test_settings(job_settings: Settings) -> Settings:
    return job_settings


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


@pytest.fixture(autouse=True)
def configured_app(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(
        update={"lexicon_path": Path(__file__).parents[1] / "fixtures" / "lexicon_small.sqlite"}
    )


async def test_new_repeat_subset_hidden_and_jobs(
    client: AsyncClient, make_user: UserFactory, db: AsyncWsSurrealConnection
) -> None:
    user, other = await make_user(), await make_user()
    owner = RecordID("user", user_key(user.id))
    headers = bearer(await login(client, user.username))
    other_headers = bearer(await login(client, other.username))
    project = (await client.post("/api/projects", headers=headers, json={"name": "Words"})).json()
    url = f"/api/projects/{project['id']}/dictionary"
    body = {"lemma_key": ["en", "run"], "selected_senses": [FLOW, MOVE, MOVE]}
    response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    expected_senses = {encode_rid(RecordID("sense", key), "sense") for key in (FLOW, MOVE)}
    assert set(result["selected_sense_ids"]) == expected_senses
    assert len(result["lexeme_ids"]) == 2
    assert len(result["membership_ids"]) == 3
    memberships = await owned(db, "includes", owner)
    assert {edge["out"] for edge in memberships} == {
        decode_rid(result["lemma_id"], "lemma"),
        *(RecordID("sense", key) for key in (FLOW, MOVE)),
    }
    assert all(not edge["hidden"] for edge in memberships)
    assert len(result["jobs"]) == 6  # Two selected senses + two lexemes x US/UK.
    jobs = await owned(db, "job", owner)
    for job in jobs:
        schema = EnrichJobPayload if job["type"] == "enrich" else AudioJobPayload
        payload = schema.model_validate(job["payload"])
        assert payload.lemma_id == result["lemma_id"] and payload.lemma_key == ["en", "run"]
        if isinstance(payload, EnrichJobPayload):
            assert payload.sense_id in expected_senses
        else:
            assert payload.accent in ("US", "UK") and payload.lexeme_id in result["lexeme_ids"]
    for job in result["jobs"]:
        assert job["status"] == "queued" and job["attempts"] == 0
        assert (await client.get(f"/api/jobs/{job['id']}", headers=headers)).json() == job
        assert (
            await client.get(f"/api/jobs/{job['id']}", headers=other_headers)
        ).status_code == 404
        assert "payload" not in job and "owner" not in job
    target = RecordID("sense", FLOW)
    await put_override(db, owner, target, {"definition": "My explanation"})
    overrides = await owned(db, "override", owner)
    dictionary = {table: await visible(db, table, owner) for table in ("lemma", "lexeme", "sense")}
    repeated = await client.post(url, headers=headers, json=body)
    assert repeated.status_code == 200 and repeated.json() == result
    assert await owned(db, "includes", owner) == memberships
    assert await owned(db, "job", owner) == jobs
    for edge in memberships:
        await set_hidden(db, edge["id"], owner, True)
    subset = await client.post(
        url, headers=headers, json={"lemma_key": ["en", "run"], "selected_senses": [MOVE]}
    )
    assert subset.status_code == 200, subset.text
    assert subset.json()["selected_sense_ids"] == [encode_rid(RecordID("sense", MOVE), "sense")]
    after = await owned(db, "includes", owner)
    assert {edge["id"] for edge in after} == {edge["id"] for edge in memberships}
    for edge in after:
        original = next(row for row in memberships if row["id"] == edge["id"])
        assert edge["added_at"] == original["added_at"]
        assert edge["hidden"] == (edge["out"] == target)
    assert await owned(db, "override", owner) == overrides
    assert await owned(db, "job", owner) == jobs
    assert {table: await visible(db, table, owner) for table in dictionary} == dictionary
    # The same user's second project reuses owner/target jobs, but gets its own memberships.
    second = (await client.post("/api/projects", headers=headers, json={"name": "More"})).json()
    again = await client.post(
        f"/api/projects/{second['id']}/dictionary", headers=headers, json=body
    )
    assert again.status_code == 200 and again.json()["jobs"] == result["jobs"]
    assert len(await owned(db, "includes", owner)) == 6
    assert await owned(db, "job", owner) == jobs


async def test_invalid_foreign_projects_and_selection_are_side_effect_free(
    client: AsyncClient, make_user: UserFactory, db: AsyncWsSurrealConnection
) -> None:
    user, other = await make_user(), await make_user()
    owner = RecordID("user", user_key(user.id))
    headers = bearer(await login(client, user.username))
    foreign_headers = bearer(await login(client, other.username))
    project = (await client.post("/api/projects", headers=headers, json={"name": "Own"})).json()
    foreign = (
        await client.post("/api/projects", headers=foreign_headers, json={"name": "Other"})
    ).json()
    tables = ("lemma", "lexeme", "sense", "has_lexeme", "has_sense", "includes", "job")
    before = {table: await visible(db, table, owner) for table in tables}
    body = {"lemma_key": ["en", "decision"], "selected_senses": []}
    for project_id in (
        foreign["id"],
        encode_rid(RecordID("project", uuid4().hex), "project"),
        "malformed",
    ):
        response = await client.post(
            f"/api/projects/{project_id}/dictionary", headers=headers, json=body
        )
        assert response.status_code == 404 and response.json()["code"] == "project.not_found"
    url = f"/api/projects/{project['id']}/dictionary"
    for lemma, selection, code, status in (
        (["en", "decision"], [MOVE], "dictionary.invalid_selection", 422),
        (["en", "zzqxyunknown"], [], "dictionary.not_found", 404),
        (
            ["en", "run"],
            [sense_key("en", "run", "verb", source_sense_id="missing")],
            "dictionary.invalid_selection",
            422,
        ),
    ):
        response = await client.post(
            url, headers=headers, json={"lemma_key": lemma, "selected_senses": selection}
        )
        assert response.status_code == status and response.json()["code"] == code
    assert {table: await visible(db, table, owner) for table in tables} == before
    assert await owned(db, "includes", RecordID("user", user_key(other.id))) == []
    assert await owned(db, "job", RecordID("user", user_key(other.id))) == []


async def test_auth_validation_and_empty_selection(
    client: AsyncClient, make_user: UserFactory, db: AsyncWsSurrealConnection
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    project = (await client.post("/api/projects", headers=headers, json={"name": "Empty"})).json()
    url = f"/api/projects/{project['id']}/dictionary"
    body = {"lemma_key": ["en", "run"], "selected_senses": []}
    assert (await client.post(url, json=body)).status_code == 401
    pending = await make_user(must_change_password=True)
    gated = await client.post(url, json=body, headers=bearer(await login(client, pending.username)))
    assert gated.status_code == 403
    for invalid in (
        {},
        {"lemma_key": ["en", "run"]},
        {**body, "owner": user.id},
        {**body, "lemma_key": ["en", "RUN"]},
        {**body, "selected_senses": None},
        {**body, "selected_senses": [["en", "run"]]},
        {**body, "selected_senses": [["en", "run", "verb", True, "run-move"]]},
    ):
        assert (await client.post(url, headers=headers, json=invalid)).status_code == 422
    response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["selected_sense_ids"] == [] and len(result["membership_ids"]) == 1
    assert {job["type"] for job in result["jobs"]} == {"audio"}
    assert len(await owned(db, "includes", RecordID("user", user_key(user.id)))) == 1
