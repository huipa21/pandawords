import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid, encode_rid
from app.db import dictionary_schema_test_support as schema
from app.db import jobs as job_repository
from app.db import media_test_support as support
from app.domain.identity import user_key
from app.domain.jobs import JobCreate
from app.services import jobs
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory
from tests.llm_support import provider as provider
from tests.mnemonic_support import finish, target

pytestmark = pytest.mark.integration
TEXT = "Imagine running shoes racing toward a bus to remember moving quickly."


@pytest.fixture
def test_settings(job_settings: Settings) -> Settings:
    return job_settings


@pytest.fixture
async def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


@pytest.fixture
def settings(test_settings: Settings) -> Settings:
    return test_settings.model_copy(
        update={
            "deepseek_api_key": "sk-test-secret",
            "llm_max_retries": 0,
            "llm_timeout_seconds": 30,
        }
    )


@pytest.mark.parametrize("table", ["lemma", "lexeme", "sense"])
async def test_note_kinds_and_explicit_suggestion_save(
    client: AsyncClient,
    app: FastAPI,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    settings: Settings,
    provider: dict[str, Any],
    table: str,
) -> None:
    app.state.settings = settings
    user, other = await make_user(), await make_user()
    headers = bearer(await login(client, user.username))
    other_headers = bearer(await login(client, other.username))
    query = await target(db, table)
    provider["content"] = json.dumps({"text": TEXT})
    ordinary = (
        await client.post("/api/notes", headers=headers, json={**query, "text": "PRIVATE"})
    ).json()
    response = await client.post("/api/notes/suggestions", headers=headers, json=query)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    queued = response.json()
    assert queued["status"] == "pending" and provider["calls"] == 0
    job = await job_repository.read(db, queued["job_id"], user.id)
    assert job is not None and job.owner == user.id
    assert set(job.payload) == {"target_table", "target_id", "key"}
    path = "/api/notes/suggestions/" + job.id
    assert (await client.get(path, headers=other_headers)).status_code == 404
    assert (await client.get(path)).status_code == 401
    await finish(db, settings, job.id)
    ready = await client.get(path, headers=headers)
    assert ready.json()["text"] == TEXT and ready.json()["status"] == "ready"
    assert b"PRIVATE" not in provider["request"].content
    assert (await client.get("/api/notes", headers=headers, params=query)).json() == [ordinary]
    app.state.settings = settings.model_copy(update={"deepseek_api_key": ""})
    assert (await client.post("/api/notes/suggestions", headers=headers, json=query)).json()[
        "text"
    ] == TEXT
    assert (await client.post("/api/notes/suggestions", headers=other_headers, json=query)).json()[
        "reason"
    ] == "disabled"
    assert provider["calls"] == 1
    created = await client.post(
        "/api/notes", headers=headers, json={**query, "kind": "mnemonic", "text": TEXT + " Edited"}
    )
    assert created.status_code == 201
    note = created.json()
    assert (
        await client.patch("/api/notes/" + note["id"], headers=headers, json={"text": "My hint"})
    ).json()["kind"] == "mnemonic"
    assert (await client.get("/api/notes/" + ordinary["id"], headers=headers)).json() == ordinary
    assert (
        await client.delete("/api/notes/" + note["id"], headers=other_headers)
    ).status_code == 404
    assert (await client.delete("/api/notes/" + note["id"], headers=headers)).status_code == 204


@pytest.mark.parametrize(
    "content,change,reason",
    [
        ("bad JSON", {}, "invalid_response"),
        ('{"text":""}', {}, "invalid_response"),
        (json.dumps({"text": "x" * 2001}), {}, "invalid_response"),
        ('{"text":"<script>alert(1)</script>"}', {}, "rejected_response"),
        ('{"text":"**marked up**"}', {}, "rejected_response"),
        ('{"text":"  "}', {}, "rejected_response"),
        ('{"text":"a\\u0000b"}', {}, "rejected_response"),
        ('{"text":"hint","extra":"secret"}', {}, "invalid_response"),
        ("{}", {"llm_timeout_seconds": 0.01}, "timeout"),
        ("{}", {"llm_daily_budget": 0}, "budget_exhausted"),
        ("{}", {"deepseek_api_key": ""}, "disabled"),
        ("{}", {}, "provider_error"),
    ],
)
async def test_optional_failures_leave_notes_untouched(
    client: AsyncClient,
    app: FastAPI,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    settings: Settings,
    provider: dict[str, Any],
    content: str,
    change: dict[str, Any],
    reason: str,
) -> None:
    settings = settings.model_copy(update=change)
    app.state.settings = settings
    provider.update(
        content=content,
        sleep=reason == "timeout",
        status=503 if reason == "provider_error" else 200,
    )
    user = await make_user()
    headers = bearer(await login(client, user.username))
    query = await target(db)
    result = (await client.post("/api/notes/suggestions", headers=headers, json=query)).json()
    if result["status"] == "pending":
        await finish(db, settings, result["job_id"])
        result = (
            await client.get("/api/notes/suggestions/" + result["job_id"], headers=headers)
        ).json()
    assert result["status"] == "unavailable" and result["reason"] == reason
    assert (await client.get("/api/notes", headers=headers, params=query)).json() == []
    provider.update(content=json.dumps({"text": TEXT}), sleep=False)
    app.state.settings = settings.model_copy(update={"llm_timeout_seconds": 30})
    if reason not in {"disabled", "budget_exhausted"}:
        retry = (await client.post("/api/notes/suggestions", headers=headers, json=query)).json()
        assert retry["status"] == "pending"


async def test_private_targets_jobs_stale_content_and_retrieval(
    client: AsyncClient,
    app: FastAPI,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    app.state.settings = settings
    user, other = await make_user(), await make_user()
    headers, foreign = (
        bearer(await login(client, user.username)),
        bearer(await login(client, other.username)),
    )
    query = await target(db, owner=user.id)
    provider["content"] = json.dumps({"text": TEXT})
    assert (
        await client.post("/api/notes/suggestions", headers=foreign, json=query)
    ).status_code == 404
    assert (await client.post("/api/notes/suggestions", json=query)).status_code == 401
    assert (
        await client.post(
            "/api/notes/suggestions", headers=headers, json={**query, "text": "private"}
        )
    ).status_code == 422
    queued = (await client.post("/api/notes/suggestions", headers=headers, json=query)).json()
    record = decode_rid(query["target_id"], "sense")
    await support.change(db, record, {"definition": "Changed before dispatch"})
    await finish(db, settings, queued["job_id"])
    result = await client.get("/api/notes/suggestions/" + queued["job_id"], headers=headers)
    assert result.json()["reason"] == "stale_content" and provider["calls"] == 0
    fresh = (await client.post("/api/notes/suggestions", headers=headers, json=query)).json()
    await finish(db, settings, fresh["job_id"])
    assert provider["calls"] == 1
    await support.change(db, record, {"owner": RecordID("user", user_key(other.id))})
    path = "/api/notes/suggestions/" + fresh["job_id"]
    assert (await client.get(path, headers=headers)).status_code == 404
    assert (await client.get(path, headers=foreign)).status_code == 404
    # Even a forged worker payload cannot dispatch against a foreign private target.
    payload = await job_repository.read(db, fresh["job_id"], user.id)
    assert payload is not None
    forged = await jobs.enqueue(
        db, JobCreate(type="mnemonic", owner=user.id, payload=payload.payload)
    )
    await finish(db, settings, forged.id)
    assert (await jobs.read(db, forged.id, user.id)).error == "invalid_scope"
    assert provider["calls"] == 1
    deleted = (await client.post("/api/notes/suggestions", headers=foreign, json=query)).json()
    assert deleted["status"] == "pending"
    await support.remove(db, record)
    await finish(db, settings, deleted["job_id"])
    assert (await jobs.read(db, deleted["job_id"], other.id)).error == "invalid_scope"
    assert provider["calls"] == 1
    assert (await client.get(path, headers=headers)).status_code == 404
    assert (
        await client.post("/api/notes/suggestions", headers=foreign, json=query)
    ).status_code == 404
    for invalid in ("invalid", encode_rid(RecordID("sense", "missing"), "sense")):
        assert (
            await client.post(
                "/api/notes/suggestions", headers=headers, json={**query, "target_id": invalid}
            )
        ).status_code == 404
    assert (await client.get("/api/notes/suggestions/invalid", headers=headers)).status_code == 404


async def test_minimal_visible_ancestry_no_overlays_and_real_budget(
    client: AsyncClient,
    app: FastAPI,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    settings: Settings,
    provider: dict[str, Any],
) -> None:
    settings = settings.model_copy(update={"llm_daily_budget": 1})
    app.state.settings = settings
    user, other = await make_user(), await make_user()
    headers = bearer(await login(client, user.username))
    lemma, lexeme, sense = await target(db, "lemma"), await target(db, "lexeme"), await target(db)
    lr, xr, sr = (
        decode_rid(item["target_id"], item["target_table"]) for item in (lemma, lexeme, sense)
    )
    await schema.relate(db, "has_lexeme", lr, xr, {})
    await schema.relate(db, "has_sense", xr, sr, {"rank": 0})
    path = "/api/dictionary/sense/" + sense["target_id"] + "/override"
    assert (
        await client.put(path, headers=headers, json={"fields": {"definition": "PRIVATE OVERLAY"}})
    ).status_code == 200
    provider["content"] = json.dumps({"text": TEXT})
    queued = (await client.post("/api/notes/suggestions", headers=headers, json=sense)).json()
    await finish(db, settings, queued["job_id"])
    sent = json.loads(provider["request"].content)["messages"][1]["content"]
    assert "PRIVATE OVERLAY" not in sent and '"lemma"' in sent and '"pos"' in sent
    original_job = queued["job_id"]
    assert (await client.get("/api/notes/suggestions/" + queued["job_id"], headers=headers)).json()[
        "text"
    ] == TEXT
    second = await target(db)
    queued = (await client.post("/api/notes/suggestions", headers=headers, json=second)).json()
    await finish(db, settings, queued["job_id"])
    assert (await client.get("/api/notes/suggestions/" + queued["job_id"], headers=headers)).json()[
        "reason"
    ] == "budget_exhausted"
    assert provider["calls"] == 1
    # Another owner cannot consume this cache; they have an independent budget.
    other_headers = bearer(await login(client, other.username))
    queued = (await client.post("/api/notes/suggestions", headers=other_headers, json=sense)).json()
    assert queued["status"] == "pending"
    await finish(db, settings, queued["job_id"])
    assert provider["calls"] == 2
    # Removing a visible ancestor invalidates the original job's content key.
    await support.remove(db, lr)
    assert (await client.get("/api/notes/suggestions/" + original_job, headers=headers)).json()[
        "reason"
    ] == "stale_content"
    original = await client.post("/api/notes/suggestions", headers=headers, json=sense)
    assert original.json()["status"] == "pending"
