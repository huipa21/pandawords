from typing import Any

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import encode_rid
from app.db import media_test_support as support
from app.domain.identity import user_key
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_notes_crud_and_cross_user_isolation(
    client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user(role="admin")
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    target = await support.target(db)
    target_id = encode_rid(target, "tag")
    query = {"target_table": "tag", "target_id": target_id}
    response = await client.post("/api/notes", headers=ah, json={**query, "text": "Remember me"})
    assert response.status_code == 201, response.text
    note = response.json()
    assert note == {**query, "id": note["id"], "kind": "note", "text": "Remember me"}
    path = f"/api/notes/{note['id']}"
    assert (await client.get(path, headers=ah)).json() == note
    assert (await client.get("/api/notes", params=query, headers=ah)).json() == [note]
    assert (await client.get("/api/notes", params=query, headers=bh)).json() == []
    for method in ("GET", "PATCH", "DELETE"):
        kwargs: dict[str, Any] = {"json": {"text": "Stolen"}} if method == "PATCH" else {}
        assert (await client.request(method, path, headers=bh, **kwargs)).status_code == 404
    response = await client.patch(path, headers=ah, json={"kind": "mnemonic", "text": "New hint"})
    assert response.status_code == 200
    assert response.json() == {**note, "kind": "mnemonic", "text": "New hint"}
    assert (await client.patch(path, headers=ah, json={})).json() == response.json()
    for body in (
        {"owner": bob.id},
        {"target_id": target_id},
        {"target_table": "sense"},
        {"kind": "invalid"},
        {"text": ""},
        {"text": " "},
        {"text": None},
    ):
        assert (await client.patch(path, headers=ah, json=body)).status_code == 422
    assert (await client.delete(path, headers=ah)).status_code == 204
    assert (await client.get(path, headers=ah)).status_code == 404
    assert (await client.get("/api/notes", params=query, headers=ah)).json() == []


async def test_notes_and_overrides_recheck_current_target_visibility(
    client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user()
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    target = await support.target(db, alice.id)
    target_id = encode_rid(target, "tag")
    query = {"target_table": "tag", "target_id": target_id}
    body = {**query, "text": "Private"}
    created = await client.post("/api/notes", headers=ah, json=body)
    assert created.status_code == 201
    note_path = f"/api/notes/{created.json()['id']}"
    override_path = f"/api/dictionary/tag/{target_id}/override"
    assert (
        await client.put(override_path, headers=ah, json={"fields": {"name": "Mine"}})
    ).status_code == 200
    assert (await client.post("/api/notes", headers=bh, json=body)).status_code == 404
    assert (await client.get("/api/notes", params=query, headers=bh)).status_code == 404
    await support.change(db, target, {"owner": RecordID("user", user_key(bob.id))})
    for method in ("GET", "PATCH", "DELETE"):
        kwargs = {"json": {"text": "Changed"}} if method == "PATCH" else {}
        assert (await client.request(method, note_path, headers=ah, **kwargs)).status_code == 404
        assert (await client.request(method, note_path, headers=bh, **kwargs)).status_code == 404
    assert (await client.get(override_path, headers=ah)).status_code == 404
    await support.remove(db, target)
    for headers in (ah, bh):
        assert (await client.post("/api/notes", headers=headers, json=body)).status_code == 404
        assert (await client.get("/api/notes", params=query, headers=headers)).status_code == 404
        for method in ("GET", "PATCH", "DELETE"):
            kwargs: dict[str, Any] = {"json": {"text": "Changed"}} if method == "PATCH" else {}
            assert (
                await client.request(method, note_path, headers=headers, **kwargs)
            ).status_code == 404
        for method in ("GET", "PUT", "PATCH", "DELETE"):
            kwargs = {"json": {"fields": {"name": "Changed"}}} if method in {"PUT", "PATCH"} else {}
            assert (
                await client.request(method, override_path, headers=headers, **kwargs)
            ).status_code == 404


async def test_notes_reject_malformed_missing_and_non_dictionary_targets(
    client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    for id in (
        "invalid",
        encode_rid(RecordID("tag", "missing"), "tag"),
        encode_rid(RecordID("user", "private"), "user"),
    ):
        body = {"target_table": "tag", "target_id": id, "text": "x"}
        assert (await client.post("/api/notes", headers=headers, json=body)).status_code == 404
        assert (
            await client.get(
                "/api/notes",
                headers=headers,
                params={
                    "target_table": "tag",
                    "target_id": id,
                },
            )
        ).status_code == 404
        for method in ("GET", "PATCH", "DELETE"):
            kwargs: dict[str, Any] = {"json": {"text": "x"}} if method == "PATCH" else {}
            assert (
                await client.request(method, f"/api/notes/{id}", headers=headers, **kwargs)
            ).status_code == 404
        for method in ("GET", "PUT", "PATCH", "DELETE"):
            kwargs = {"json": {"fields": {"name": "x"}}} if method in {"PUT", "PATCH"} else {}
            assert (
                await client.request(
                    method, f"/api/dictionary/tag/{id}/override", headers=headers, **kwargs
                )
            ).status_code == 404
    target_id = encode_rid(await support.target(db), "tag")
    for body in (
        {"target_table": "user", "target_id": target_id, "text": "x"},
        {"target_table": "tag", "target_id": target_id, "text": "x", "owner": user.id},
        {"target_table": "tag", "target_id": target_id, "text": "x", "id": target_id},
        {"target_table": "tag", "target_id": target_id, "text": "x", "kind": "invalid"},
    ):
        assert (await client.post("/api/notes", headers=headers, json=body)).status_code == 422
