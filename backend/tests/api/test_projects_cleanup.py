from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid
from app.db.dictionary_schema_test_support import create, relate, visible
from app.db.project_schema_test_support import owned, put_override
from app.domain.identity import user_key
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
URL = "/api/projects"


async def test_delete_only_removes_owner_project_and_its_memberships(
    client: AsyncClient, make_user: UserFactory, db: AsyncWsSurrealConnection
) -> None:
    alice, bob = await make_user(), await make_user()
    alice_id = RecordID("user", user_key(alice.id))
    bob_id = RecordID("user", user_key(bob.id))
    headers = bearer(await login(client, alice.username))
    bob_headers = bearer(await login(client, bob.username))
    projects = []
    for auth in (headers, headers, bob_headers):
        response = await client.post(URL, headers=auth, json={"name": "English"})
        assert response.status_code == 201
        projects.append(response.json())
    target, retained, other = [decode_rid(item["id"], "project") for item in projects]
    shared = await create(
        db,
        RecordID("sentence", uuid4().hex),
        {"text": "Run!", "lang": "en", "translation": {}, "source": "test"},
    )
    private = await create(
        db,
        RecordID("sentence", uuid4().hex),
        {"text": "My words", "lang": "en", "translation": {}, "source": "test", "owner": alice_id},
    )
    for project, owner, item, hidden in (
        (target, alice_id, shared, False),
        (target, alice_id, private, True),
        (retained, alice_id, shared, False),
        (other, bob_id, shared, False),
    ):
        await relate(
            db,
            "includes",
            project,
            item["id"],
            {"owner": owner, "hidden": hidden, "added_at": datetime.now(UTC)},
        )
    for owner in (alice_id, bob_id):
        await put_override(db, owner, shared["id"], {"text": "Personal text"})
        await create(
            db,
            RecordID("note", uuid4().hex),
            {"owner": owner, "target": shared["id"], "kind": "note", "text": "Remember"},
        )
    memberships = {owner: await owned(db, "includes", owner) for owner in (alice_id, bob_id)}
    annotations = {
        (owner, table): await owned(db, table, owner)
        for owner in (alice_id, bob_id)
        for table in ("note", "override")
    }
    sentences = await visible(db, "sentence", alice_id)
    deleted = await client.delete(f"{URL}/{projects[0]['id']}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    assert await owned(db, "includes", alice_id) == [
        edge for edge in memberships[alice_id] if edge["in"] != target
    ]
    assert await owned(db, "includes", bob_id) == memberships[bob_id]
    assert await visible(db, "sentence", alice_id) == sentences
    for (owner, table), rows in annotations.items():
        assert await owned(db, table, owner) == rows
    assert (await client.get(f"{URL}/{projects[1]['id']}", headers=headers)).json() == projects[1]
    assert (await client.get(f"{URL}/{projects[2]['id']}", headers=bob_headers)).json() == projects[
        2
    ]


async def test_delete_does_not_cascade_foreign_owned_membership(
    client: AsyncClient, make_user: UserFactory, db: AsyncWsSurrealConnection
) -> None:
    alice, bob = await make_user(), await make_user()
    alice_id = RecordID("user", user_key(alice.id))
    bob_id = RecordID("user", user_key(bob.id))
    headers = bearer(await login(client, alice.username))
    created = await client.post(URL, headers=headers, json={"name": "Inconsistent legacy data"})
    project = decode_rid(created.json()["id"], "project")
    sentence = await create(
        db,
        RecordID("sentence", uuid4().hex),
        {"text": "Run!", "lang": "en", "translation": {}, "source": "test"},
    )
    for owner in (alice_id, bob_id):
        await relate(
            db,
            "includes",
            project,
            sentence["id"],
            {"owner": owner, "hidden": False, "added_at": datetime.now(UTC)},
        )
    before = {owner: await owned(db, "includes", owner) for owner in (alice_id, bob_id)}
    response = await client.delete(f"{URL}/{created.json()['id']}", headers=headers)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "project.membership_conflict"
    assert (
        await client.get(f"{URL}/{created.json()['id']}", headers=headers)
    ).json() == created.json()
    for owner, rows in before.items():
        assert await owned(db, "includes", owner) == rows
