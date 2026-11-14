from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.auth_test_support import disable_user
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
URL = "/api/dictionary/candidates"
FIXTURE = Path(__file__).parents[1] / "fixtures" / "lexicon_small.sqlite"


@pytest.fixture
async def candidate_app(app: FastAPI) -> FastAPI:
    settings: Settings = app.state.settings
    # Replace the application setting, not a reader/service override: exercise real wiring.
    app.state.settings = settings.model_copy(update={"lexicon_path": FIXTURE})
    return app


async def test_configured_fixture_and_shared_candidates(
    candidate_app: FastAPI, client: AsyncClient, make_user: UserFactory
) -> None:
    user, other = await make_user(), await make_user()
    first = await client.post(
        URL, json={"text": " ＲＵＮ "}, headers=bearer(await login(client, user.username))
    )
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    result = first.json()
    assert result["normalized"] == "run"
    assert result["candidates"][0]["lemma"]["id"] == ["en", "run"]
    verbs = [item for item in result["candidates"][0]["lexemes"] if item["lexeme"]["pos"] == "verb"]
    assert [sense["common"] for sense in verbs[0]["senses"]] == [True, True, False]
    assert verbs[0]["senses"][0]["source_id"] == "run-move"
    assert result["sources"]
    second = await client.post(
        URL, json={"text": "run"}, headers=bearer(await login(client, other.username))
    )
    assert second.status_code == 200 and second.json() == result
    # Shared dictionary candidates contain no user data, so enabled users see identical data.
    assert "owner" not in first.text and "username" not in first.text


async def test_authentication_and_account_gates(
    candidate_app: FastAPI,
    client: AsyncClient,
    make_user: UserFactory,
    db: AsyncWsSurrealConnection,
) -> None:
    assert (await client.post(URL, json={"text": "run"})).status_code == 401
    assert (
        await client.post(URL, json={"text": "run"}, headers={"Authorization": "Bearer invalid"})
    ).status_code == 401
    pending = await make_user(must_change_password=True)
    response = await client.post(
        URL, json={"text": "run"}, headers=bearer(await login(client, pending.username))
    )
    assert (
        response.status_code == 403 and response.json()["code"] == "auth.password_change_required"
    )
    user = await make_user()
    token = await login(client, user.username)
    await disable_user(db, user.id)
    assert (await client.post(URL, json={"text": "run"}, headers=bearer(token))).status_code == 401


async def test_validation_unknown_and_inflections(
    candidate_app: FastAPI, client: AsyncClient, make_user: UserFactory
) -> None:
    headers = bearer(await login(client, (await make_user()).username))
    for body in (
        {},
        {"text": ""},
        {"text": "   "},
        {"text": 4},
        {"text": []},
        {"text": "!!!"},
        {"text": "run", "lang": "fr"},
        {"text": "x" * 201},
    ):
        response = await client.post(URL, json=body, headers=headers)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "validation.invalid"
    for text, expected in (("went", "go"), ("give up", "give up"), ("walks", "walk")):
        response = await client.post(URL, json={"text": text}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["candidates"][0]["lemma"]["text"] == expected
    response = await client.post(URL, json={"text": "zzqxyunknown"}, headers=headers)
    assert response.json() == {"normalized": "zzqxyunknown", "candidates": [], "sources": []}


async def test_missing_and_invalid_configured_artifact(
    candidate_app: FastAPI, client: AsyncClient, make_user: UserFactory, tmp_path: Path
) -> None:
    headers = bearer(await login(client, (await make_user()).username))
    for exists, code in ((False, "lexicon.missing"), (True, "lexicon.invalid")):
        path = tmp_path / "configured.sqlite"
        if exists:
            path.write_bytes(b"not a SQLite database")
        settings: Settings = candidate_app.state.settings
        candidate_app.state.settings = settings.model_copy(update={"lexicon_path": path})
        response = await client.post(URL, json={"text": "run"}, headers=headers)
        assert response.status_code == 503 and response.json()["code"] == code
