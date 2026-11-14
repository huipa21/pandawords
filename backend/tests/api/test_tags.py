import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import encode_rid
from app.db import tags_test_support as support
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def create(client: AsyncClient, headers: dict[str, str], name: str) -> dict[str, Any]:
    response = await client.post("/api/tags", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def target(record: RecordID) -> dict[str, str]:
    return {"target_table": record.table_name, "target_id": encode_rid(record, record.table_name)}


async def test_tag_crud_strict_contract_and_isolation(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
) -> None:
    alice, bob = await make_user(), await make_user(role="admin")
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    tag = await create(client, ah, "  Travel  ")
    assert tag["name"] == "Travel" and not tag["readonly"]
    path = f"/api/tags/{tag['id']}"
    assert (await client.get(path, headers=ah)).json() == tag
    assert tag in (await client.get("/api/tags", headers=ah)).json()
    assert tag not in (await client.get("/api/tags", headers=bh)).json()
    for method in ("GET", "PATCH", "DELETE"):
        kwargs: dict[str, Any] = {"json": {"name": "stolen"}} if method == "PATCH" else {}
        assert (await client.request(method, path, headers=bh, **kwargs)).status_code == 404
    changed = await client.patch(path, headers=ah, json={"name": "Science", "kind": "concept"})
    assert changed.status_code == 200 and changed.json()["kind"] == "concept"
    for body in (
        {"owner": bob.id},
        {"id": tag["id"]},
        {"unexpected": True},
        {"name": ""},
        {"name": " "},
        {"name": "x" * 201},
        {"kind": "unknown"},
    ):
        assert (
            await client.post("/api/tags", headers=ah, json={"name": "x", **body})
        ).status_code == 422
        assert (await client.patch(path, headers=ah, json=body)).status_code == 422
    for body in ({"name": None}, {"kind": None}):
        assert (await client.patch(path, headers=ah, json=body)).status_code == 422
    shared = await support.target(db, "tag")
    shared_path = f"/api/tags/{encode_rid(shared, 'tag')}"
    assert (await client.get(shared_path, headers=ah)).json()["readonly"]
    for method in ("PATCH", "DELETE"):
        kwargs = {"json": {"name": "takeover"}} if method == "PATCH" else {}
        assert (await client.request(method, shared_path, headers=ah, **kwargs)).status_code == 403
    assert (
        await client.post(
            "/api/tags",
            headers=ah,
            json={
                "name": "takeover",
                "id": encode_rid(shared, "tag"),
            },
        )
    ).status_code == 422
    assert (await client.delete(path, headers=ah)).status_code == 204
    assert (await client.get(path, headers=ah)).status_code == 404


@pytest.mark.parametrize("table", ["sense", "morpheme", "tag"])
async def test_assignment_idempotency_ownership_and_independent_visibility(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    table: Any,
) -> None:
    alice, bob = await make_user(), await make_user()
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    shared, private = await support.target(db, table), await support.target(db, table, bob.id)
    tag = await create(client, ah, "Own")
    shared_tag = await support.target(db, "tag")
    tag_path = f"/api/tags/{tag['id']}/members"
    body = target(shared)
    for _ in range(2):
        assert (await client.put(tag_path, headers=ah, json=body)).status_code == 204
    assert len(await support.edges(db, shared)) == 1
    assert (await client.get("/api/tags/assignments", headers=ah, params=body)).json() == [
        {"tag": tag, "readonly": False},
    ]
    assert (await client.get("/api/tags/assignments", headers=bh, params=body)).json() == []
    assert (await client.put(tag_path, headers=bh, json=body)).status_code == 404
    assert (await client.delete(tag_path, headers=bh, params=body)).status_code == 404
    assert (await client.put(tag_path, headers=ah, json=target(private))).status_code == 404
    assert (await client.delete(tag_path, headers=ah, params=target(private))).status_code == 404
    assert (
        await client.get("/api/tags/assignments", headers=ah, params=target(private))
    ).status_code == 404
    # Neither a visible edge nor a visible source makes a foreign endpoint visible.
    foreign_tag = await support.target(db, "tag", bob.id)
    await support.edge(db, shared, foreign_tag, alice.id)
    await support.edge(db, private, shared_tag, alice.id)
    # A foreign-owned edge between two shared endpoints must remain private.
    await support.edge(db, shared, shared_tag, bob.id)
    assert len((await client.get("/api/tags/assignments", headers=ah, params=body)).json()) == 1
    shared_path = f"/api/tags/{encode_rid(shared_tag, 'tag')}/members"
    await support.edge(db, shared, shared_tag, None)
    assert (await client.put(shared_path, headers=ah, json=body)).status_code == 204
    assert (await client.delete(shared_path, headers=ah, params=body)).status_code == 204
    memberships = (await client.get("/api/tags/assignments", headers=ah, params=body)).json()
    assert any(item["tag"]["readonly"] and item["readonly"] for item in memberships)
    for _ in range(2):
        assert (await client.delete(tag_path, headers=ah, params=body)).status_code == 204
    assert all(
        item["readonly"]
        for item in (await client.get("/api/tags/assignments", headers=ah, params=body)).json()
    )


async def test_assignment_contract_and_missing_ids(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    tag = await create(client, headers, "Tag")
    record = await support.target(db, "sense")
    body = target(record)
    path = f"/api/tags/{tag['id']}/members"
    for extra in ({"owner": user.id}, {"id": "injected"}, {"unknown": 1}):
        assert (await client.put(path, headers=headers, json={**body, **extra})).status_code == 422
        assert (
            await client.delete(path, headers=headers, params={**body, **extra})
        ).status_code == 422
        assert (
            await client.get("/api/tags/assignments", headers=headers, params={**body, **extra})
        ).status_code == 422
        assert (await client.get("/api/tags", headers=headers, params=extra)).status_code == 422
    for table in ("user", "lemma", "lexeme", "sentence", "passage", "member_of"):
        invalid = {**body, "target_table": table}
        assert (await client.put(path, headers=headers, json=invalid)).status_code == 422
        assert (await client.delete(path, headers=headers, params=invalid)).status_code == 422
        assert (
            await client.get("/api/tags/assignments", headers=headers, params=invalid)
        ).status_code == 422
    for id in ("malformed", encode_rid(RecordID("tag", "missing"), "tag"), tag["id"]):
        invalid = {**body, "target_id": id}
        assert (await client.put(path, headers=headers, json=invalid)).status_code == 404
        assert (await client.delete(path, headers=headers, params=invalid)).status_code == 404
        assert (
            await client.get("/api/tags/assignments", headers=headers, params=invalid)
        ).status_code == 404


async def test_tag_endpoints_require_authentication(client: AsyncClient) -> None:
    for method, path, body in (
        ("GET", "/api/tags", None),
        ("POST", "/api/tags", {"name": "Private"}),
        ("GET", "/api/tags/assignments?target_table=tag&target_id=private", None),
        ("GET", "/api/tags/private", None),
        ("PATCH", "/api/tags/private", {"name": "Private"}),
        ("DELETE", "/api/tags/private", None),
        ("PUT", "/api/tags/private/members", {"target_table": "tag", "target_id": "private"}),
        ("DELETE", "/api/tags/private/members?target_table=tag&target_id=private", None),
    ):
        response = await client.request(method, path, json=body)
        assert response.status_code == 401


async def test_hierarchy_cycles_concurrent_opposing_edits_and_retries(
    client: AsyncClient,
    make_user: UserFactory,
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    a, b, c = [await create(client, headers, name) for name in ("a", "b", "c")]

    async def assign(child: dict, parent: dict) -> int:
        return (
            await client.put(
                f"/api/tags/{parent['id']}/members",
                headers=headers,
                json={
                    "target_table": "tag",
                    "target_id": child["id"],
                },
            )
        ).status_code

    assert await assign(a, a) == 409
    results = await asyncio.gather(assign(a, b), assign(b, a))
    assert sorted(results) == [204, 409]
    child, parent = (a, b) if results[0] == 204 else (b, a)
    assert await assign(parent, c) == 204
    assert await assign(c, child) == 409
    assert await assign(child, parent) == 204
    assert sorted(await asyncio.gather(assign(child, c), assign(child, c))) == [204, 204]


async def test_delete_cleans_only_owned_incident_edges_and_rolls_back(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.record_ids import decode_rid
    from app.db import tags as repository

    alice, bob = await make_user(), await make_user()
    headers = bearer(await login(client, alice.username))
    tag = await create(client, headers, "Delete")
    record = decode_rid(tag["id"], "tag")
    shared = await support.target(db, "tag")
    incoming = await support.edge(db, shared, record, alice.id)
    outgoing = await support.edge(db, record, shared, alice.id)
    other = await support.edge(db, shared, shared, alice.id)
    original = repository._rows

    async def fail_delete(connection: Any, query: str, *args: Any, **kwargs: Any) -> Any:
        if query.startswith("DELETE $tag"):
            raise RuntimeError("Simulated failure")
        return await original(connection, query, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(repository, "_rows", fail_delete)
        with pytest.raises(RuntimeError, match="Simulated failure"):
            await repository.manage(db, alice.id, record, "delete")
    assert {row["id"] for row in await support.edges(db, record)} == {incoming, outgoing}
    foreign = await support.edge(db, shared, record, bob.id)
    path = f"/api/tags/{tag['id']}"
    assert (await client.delete(path, headers=headers)).status_code == 409
    assert {row["id"] for row in await support.edges(db, record)} == {incoming, outgoing, foreign}
    await support.remove_edge(db, foreign)
    assert (await client.delete(path, headers=headers)).status_code == 204
    assert {row["id"] for row in await support.edges(db, shared)} == {other}
