import asyncio
from hashlib import sha256
from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import encode_rid
from app.db.dictionary_schema_test_support import create, relate
from tests.api.test_graph import NOW, PROJECT_FIELDS, Fixture
from tests.api.test_graph import graph as graph

pytestmark = pytest.mark.integration
KINDS = ["synonym", "antonym", "hypernym", "hyponym", "confusable", "collocation", "default"]


def payload(graph: Fixture, kind: str = "antonym") -> dict[str, str]:
    return {
        "start": encode_rid(graph.nodes["sense2"], "sense"),
        "end": encode_rid(graph.nodes["sense"], "sense"),
        "type": kind,
    }


async def listing(client: AsyncClient, graph: Fixture) -> list[dict]:
    result = await client.get(
        "/api/relations",
        headers=graph.headers,
        params={"sense_id": payload(graph)["start"]},
    )
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize("kind", KINDS)
async def test_types_retry_delete(
    graph: Fixture, client: AsyncClient, db: AsyncWsSurrealConnection, kind: str
) -> None:
    data = payload(graph, kind)
    self_link = await client.post(
        "/api/relations", headers=graph.headers, json={**data, "end": data["start"]}
    )
    assert self_link.status_code == 422
    assert self_link.json()["code"] == "relation.self_link"
    made = await client.post("/api/relations", headers=graph.headers, json=data)
    assert made.status_code == 201, made.text
    edge = made.json()["relation"]
    assert edge == {
        **data,
        "id": edge["id"],
        "readonly": False,
        "source": "user",
        "start_label": "Second",
        "end_label": "Meaning",
    }
    retry = await client.post("/api/relations", headers=graph.headers, json=data)
    assert retry.status_code == 200, retry.text
    assert retry.json() == {"relation": edge, "created": False}
    assert sum(row["id"] == edge["id"] for row in await listing(client, graph)) == 1
    removed = await client.delete(f"/api/relations/{edge['id']}", headers=graph.headers)
    assert removed.status_code == 204, removed.text
    assert edge["id"] not in {row["id"] for row in await listing(client, graph)}
    sense = await db.select(graph.nodes["sense"])
    assert sense is not None and sense["definition"] == "Meaning"


async def test_concurrent_retry_and_owner_independence(
    graph: Fixture, client: AsyncClient, db: AsyncWsSurrealConnection
) -> None:
    data = payload(graph)
    results = await asyncio.gather(
        *[client.post("/api/relations", headers=graph.headers, json=data) for _ in range(4)]
    )
    assert sorted(result.status_code for result in results) == [200, 200, 200, 201], [
        result.text for result in results
    ]
    assert len({result.json()["relation"]["id"] for result in results}) == 1
    edge_id = results[0].json()["relation"]["id"]
    assert (
        await client.delete(f"/api/relations/{edge_id}", headers=graph.other_headers)
    ).status_code == 404
    # Give Bob legitimate selections of the same shared endpoints.
    project = RecordID("project", uuid4().hex)
    await create(db, project, {**PROJECT_FIELDS, "owner": graph.other})
    for sense in (graph.nodes["sense"], graph.nodes["sense2"]):
        await relate(
            db, "includes", project, sense, {"owner": graph.other, "hidden": False, "added_at": NOW}
        )
    other = await client.post("/api/relations", headers=graph.other_headers, json=data)
    assert other.status_code == 201, other.text
    assert other.json()["relation"]["id"] != edge_id
    await client.delete(
        f"/api/relations/{other.json()['relation']['id']}", headers=graph.other_headers
    )
    assert edge_id in {row["id"] for row in await listing(client, graph)}


async def test_visibility_ownership_shared_immutability_and_injection(
    graph: Fixture, client: AsyncClient, db: AsyncWsSurrealConnection
) -> None:
    data = payload(graph)
    for headers in ({}, graph.other_headers):
        expected = 401 if not headers else 404
        assert (
            await client.post("/api/relations", headers=headers, json=data)
        ).status_code == expected
        assert (
            await client.get("/api/relations", headers=headers, params={"sense_id": data["start"]})
        ).status_code == expected
    for extra in ({"owner": str(graph.other)}, {"id": "injected"}, {"source": "dictionary"}):
        assert (
            await client.post("/api/relations", headers=graph.headers, json={**data, **extra})
        ).status_code == 422
    for change in (
        {"type": "unsupported"},
        {"start": data["end"]},
        {"start": encode_rid(graph.nodes["lemma"], "lemma")},
        {"end": "sense:raw; DELETE user;"},
    ):
        assert (
            await client.post("/api/relations", headers=graph.headers, json={**data, **change})
        ).status_code == 422
    shared = await relate(
        db,
        "relates_to",
        graph.nodes["sense2"],
        graph.nodes["sense"],
        {"type": "antonym", "source": "dictionary"},
    )
    shared_id = encode_rid(shared["id"], "relates_to")
    assert next(row for row in await listing(client, graph) if row["id"] == shared_id)["readonly"]
    assert (
        await client.delete(f"/api/relations/{shared_id}", headers=graph.headers)
    ).status_code == 404
    made = await client.post("/api/relations", headers=graph.headers, json=data)
    assert made.status_code == 201, made.text
    own_id = made.json()["relation"]["id"]
    assert (await client.delete(f"/api/relations/{own_id}")).status_code == 401
    # Edge ownership cannot authorize a now-foreign endpoint.
    await db.update(graph.nodes["sense2"]).merge({"owner": graph.other})
    assert (
        await client.post("/api/relations", headers=graph.headers, json=data)
    ).status_code == 404
    assert (
        await client.get(
            "/api/relations", headers=graph.headers, params={"sense_id": data["start"]}
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/relations/{own_id}", headers=graph.headers)
    ).status_code == 404
    visible_end = await client.get(
        "/api/relations", headers=graph.headers, params={"sense_id": data["end"]}
    )
    assert visible_end.status_code == 200, visible_end.text
    assert visible_end.json() == []
    await db.update(graph.nodes["sense2"]).merge({"owner": graph.user})
    # Owned senses need no selection; hiding a shared sense really removes authorization.
    assert (
        await client.post("/api/relations", headers=graph.headers, json=data)
    ).status_code == 200
    await db.update(graph.memberships["sense"]).merge({"hidden": True})
    assert (
        await client.post("/api/relations", headers=graph.headers, json=data)
    ).status_code == 404
    assert (
        await client.delete(f"/api/relations/{own_id}", headers=graph.headers)
    ).status_code == 404
    assert await db.select(shared["id"])


async def test_unselected_shared_sense_and_foreign_edges_are_not_visible(
    graph: Fixture, client: AsyncClient, db: AsyncWsSurrealConnection
) -> None:
    data = payload(graph)
    await db.delete(graph.memberships["sense2"])
    assert (
        await client.post("/api/relations", headers=graph.headers, json=data)
    ).status_code == 404
    hidden = await client.get(
        "/api/relations", headers=graph.headers, params={"sense_id": data["end"]}
    )
    assert hidden.status_code == 200 and hidden.json() == []
    # An owner-visible endpoint is still insufficient to expose foreign-owned edges.
    await db.update(graph.nodes["sense2"]).merge({"owner": graph.user})
    foreign = await relate(
        db,
        "relates_to",
        graph.nodes["sense2"],
        graph.nodes["sense"],
        {"owner": graph.other, "type": "antonym", "source": "user"},
    )
    assert encode_rid(foreign["id"], "relates_to") not in {
        row["id"] for row in await listing(client, graph)
    }
    seeds = await client.get(
        "/api/graph/seeds", headers=graph.headers, params={"node_types": "sense", "page_size": 1}
    )
    assert seeds.status_code == 200, seeds.text
    assert len(seeds.json()) == 1 and seeds.json()[0]["table"] == "sense"
    # Even a collision with the deterministic identity must not overwrite protected data.
    key = sha256(
        f"{graph.user}\0{graph.nodes['sense2']}\0{graph.nodes['sense']}\0antonym".encode()
    ).hexdigest()
    collision = RecordID("relates_to", key)
    await relate(
        db,
        "relates_to",
        graph.nodes["sense2"],
        graph.nodes["sense"],
        {"type": "antonym", "source": "dictionary"},
        record=collision,
    )
    result = await client.post("/api/relations", headers=graph.headers, json=data)
    assert result.status_code == 409, result.text
    stored = await db.select(collision)
    assert stored is not None and stored["source"] == "dictionary"
    await db.update(collision).merge({"owner": graph.other})
    result = await client.post("/api/relations", headers=graph.headers, json=data)
    assert result.status_code == 409, result.text
    stored = await db.select(collision)
    assert stored is not None and stored["owner"] == graph.other
