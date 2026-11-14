from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient, Response
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import encode_rid
from app.db.dictionary import RELATIONS, TABLE_FIELDS
from app.db.dictionary_schema_test_support import create, relate
from app.domain.graph import GraphQuery
from app.domain.identity import user_key, user_subject
from app.services.graph import read
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 14, tzinfo=UTC)
PROJECT_FIELDS = {
    "name": "Graph",
    "description": "",
    "target_lang": "en",
    "source_lang": "zh",
    "plan": {"daily_new": 10},
    "created_at": NOW,
}


@dataclass
class Fixture:
    headers: dict[str, str]
    other_headers: dict[str, str]
    user: RecordID
    other: RecordID
    project: RecordID
    nodes: dict[str, RecordID]
    memberships: dict[str, RecordID]

    async def get(self, client: AsyncClient, focus: str = "lemma", **params: Any) -> Response:
        return await client.get(
            "/api/graph",
            headers=self.headers,
            params={"focus_id": encode_rid(self.nodes[focus], focus.rstrip("2")), **params},
        )


@pytest.fixture
async def graph(
    client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> Fixture:
    alice, bob = await make_user(), await make_user()
    user, other = RecordID("user", user_key(alice.id)), RecordID("user", user_key(bob.id))
    project = RecordID("project", uuid4().hex)
    await create(db, project, {"owner": user, **PROJECT_FIELDS})
    nodes: dict[str, RecordID] = {}
    memberships: dict[str, RecordID] = {}
    contents: dict[str, dict[str, Any]] = {
        "lemma": {
            "text": uuid4().hex,
            "lang": "en",
            "kind": "phrase",
            "freq_zipf": 1,
            "exam_tags": [],
            "source": "custom",
        },
        "lexeme": {"pos": "verb", "etymology_no": 1, "forms": [], "pron": []},
        "lexeme2": {"pos": "noun", "etymology_no": 1, "forms": [], "pron": []},
        "sense": {
            "definition": "Meaning",
            "gloss": {"zh": "意思"},
            "register": [],
            "domain": [],
            "examples": [],
            "rank": 0,
            "common": True,
            "source": "custom",
        },
        "sense2": {
            "definition": "Second",
            "gloss": {},
            "register": [],
            "domain": [],
            "examples": [],
            "rank": 1,
            "common": False,
            "source": "custom",
        },
        "morpheme": {"text": "pre-", "type": "prefix", "meaning": "before"},
        "tag": {"kind": "custom", "name": "Group"},
        "sentence": {"text": "A sentence.", "lang": "en", "translation": {}, "source": "custom"},
        "passage": {"title": "Title", "text": "Text.", "lang": "en", "source": "custom"},
    }
    for name, content in contents.items():
        record = RecordID(name.rstrip("2"), uuid4().hex)
        nodes[name] = record
        # Own records are visible without project selections.
        if name in {"sentence", "passage", "morpheme", "tag"}:
            content["owner"] = user
        await create(db, record, content)
        if name not in {"sentence", "passage", "morpheme", "tag"}:
            edge = await relate(
                db,
                "includes",
                project,
                record,
                {"owner": user, "hidden": False, "added_at": NOW},
            )
            memberships[name] = edge["id"]
    for relation, start, end, fields in [
        ("has_lexeme", "lemma", "lexeme", {}),
        ("has_sense", "lexeme", "sense", {"rank": 0}),
        ("composed_of", "lexeme", "morpheme", {"order": 0}),
        ("derives_to", "lexeme", "lexeme2", {"via": "suffix"}),
        ("relates_to", "sense", "sense2", {"type": "synonym", "source": "custom"}),
        ("member_of", "sense", "tag", {}),
        ("contains", "lemma", "lexeme2", {"position": 0}),
        ("used_in", "sense", "sentence", {"span": [0, 1]}),
        ("part_of", "sentence", "passage", {"order": 0}),
    ]:
        await relate(db, relation, nodes[start], nodes[end], {**fields, "owner": user})
    return Fixture(
        bearer(await login(client, alice.username)),
        bearer(await login(client, bob.username)),
        user,
        other,
        project,
        nodes,
        memberships,
    )


async def test_seed_discovery_visibility_search_and_paging(
    graph: Fixture, client: AsyncClient, db: AsyncWsSurrealConnection
) -> None:
    response = await client.get("/api/graph/seeds", headers=graph.headers)
    assert response.status_code == 200, response.text
    expected = {encode_rid(record, name.rstrip("2")) for name, record in graph.nodes.items()}
    assert {node["id"] for node in response.json()} == expected
    assert response.headers["cache-control"] == "no-store"
    other = await client.get("/api/graph/seeds", headers=graph.other_headers)
    assert other.json() == []
    project_id = encode_rid(graph.project, "project")
    scoped = await client.get(
        "/api/graph/seeds", headers=graph.headers, params={"project_id": project_id}
    )
    assert scoped.status_code == 200, scoped.text
    assert encode_rid(graph.nodes["tag"], "tag") not in {node["id"] for node in scoped.json()}
    denied = await client.get(
        "/api/graph/seeds", headers=graph.other_headers, params={"project_id": project_id}
    )
    assert denied.status_code == 404
    search = await client.get(
        "/api/graph/seeds", headers=graph.headers, params={"q": "MEANING", "page_size": 1}
    )
    assert [node["id"] for node in search.json()] == [encode_rid(graph.nodes["sense"], "sense")]
    await create(
        db,
        RecordID("override", [graph.user, graph.nodes["sense"]]),
        {"owner": graph.user, "fields": {"definition": "Overridden label"}, "updated_at": NOW},
    )
    effective = await client.get(
        "/api/graph/seeds", headers=graph.headers, params={"q": "OVERRIDDEN"}
    )
    assert effective.json()[0]["fields"]["definition"] == "Overridden label"
    second = await client.get(
        "/api/graph/seeds",
        headers=graph.headers,
        params={"q": "MEANING", "page_size": 1, "page": 2},
    )
    assert second.json() == []
    await db.update(graph.memberships["lemma"]).merge({"hidden": True})
    hidden = await client.get("/api/graph/seeds", headers=graph.headers)
    hidden_ids = {node["id"] for node in hidden.json()}
    assert encode_rid(graph.nodes["lemma"], "lemma") not in hidden_ids
    assert encode_rid(graph.nodes["sense"], "sense") not in hidden_ids
    assert encode_rid(graph.nodes["tag"], "tag") in hidden_ids


async def test_depth_direction_order_effective_fields(
    graph: Fixture, client: AsyncClient, db: AsyncWsSurrealConnection
) -> None:
    await read(
        db,
        user_subject(str(graph.user.id)),
        GraphQuery(focus_id=encode_rid(graph.nodes["lemma"], "lemma"), depth=0),
    )
    zero = await graph.get(client, depth=0)
    assert zero.status_code == 200, zero.text
    assert len(zero.json()["nodes"]) == 1 and zero.json()["edges"] == []
    incoming = await graph.get(client, direction="incoming", depth=3)
    assert len(incoming.json()["nodes"]) == 1
    outgoing = await graph.get(client, depth=1, direction="outgoing")
    assert {node["table"] for node in outgoing.json()["nodes"]} == {"lemma", "lexeme"}
    full = await graph.get(client, "lexeme", depth=3)
    assert full.status_code == 200, full.text
    assert len(full.json()["nodes"]) == 9
    assert {edge["table"] for edge in full.json()["edges"]} == set(RELATIONS)
    assert full.json() == (await graph.get(client, "lexeme", depth=3)).json()
    assert full.headers["cache-control"] == "no-store"
    nodes = full.json()["nodes"]
    assert nodes == sorted(nodes, key=lambda node: (node["table"], node["id"]))
    assert full.json()["edges"] == sorted(
        full.json()["edges"],
        key=lambda edge: (edge["table"], edge["start"], edge["end"], edge["id"]),
    )
    raw = full.text
    assert '"owner"' not in raw and str(graph.user) not in raw and "lemma:" not in raw
    for edge in full.json()["edges"]:
        assert edge["start"] in {node["id"] for node in nodes}
        assert edge["end"] in {node["id"] for node in nodes}
    await create(
        db,
        RecordID("override", [graph.user, graph.nodes["sense"]]),
        {"owner": graph.user, "fields": {"definition": "Effective"}, "updated_at": NOW},
    )
    effective = (await graph.get(client, "sense", depth=0)).json()
    assert effective["nodes"][0]["fields"]["definition"] == "Effective"
    # Rendering always retains stored edge orientation, even on incoming expansion.
    reverse = (await graph.get(client, "lexeme", depth=1, direction="incoming")).json()
    edge = next(edge for edge in reverse["edges"] if edge["table"] == "has_lexeme")
    assert edge["start"] == encode_rid(graph.nodes["lemma"], "lemma")
    assert edge["end"] == encode_rid(graph.nodes["lexeme"], "lexeme")


@pytest.mark.parametrize("table", list(TABLE_FIELDS))
async def test_each_node_filter(graph: Fixture, client: AsyncClient, table: str) -> None:
    response = await graph.get(client, table, depth=3, node_types=[table])
    assert response.status_code == 200, response.text
    assert {node["table"] for node in response.json()["nodes"]} == {table}


@pytest.mark.parametrize(
    ("relation", "focus"),
    [
        ("has_lexeme", "lemma"),
        ("has_sense", "lexeme"),
        ("composed_of", "lexeme"),
        ("derives_to", "lexeme"),
        ("relates_to", "sense"),
        ("member_of", "sense"),
        ("contains", "lemma"),
        ("used_in", "sense"),
        ("part_of", "sentence"),
    ],
)
async def test_each_relation_filter(
    graph: Fixture, client: AsyncClient, relation: str, focus: str
) -> None:
    response = await graph.get(client, focus, depth=3, relation_types=[relation])
    assert response.status_code == 200, response.text
    assert {edge["table"] for edge in response.json()["edges"]} == {relation}
    assert len(response.json()["nodes"]) == 2


async def test_hidden_ancestors_and_project_union(
    graph: Fixture, client: AsyncClient, db: AsyncWsSurrealConnection
) -> None:
    await db.update(graph.memberships["lemma"]).merge({"hidden": True})
    assert (await graph.get(client, "sense")).status_code == 404
    assert (await graph.get(client, "lexeme")).status_code == 404
    await db.delete(graph.memberships["lexeme"])
    assert (await graph.get(client, "sense")).status_code == 404
    # Own dictionary content is independently authorized even without selections.
    assert (await graph.get(client, "sentence", depth=0)).status_code == 200
    project = RecordID("project", uuid4().hex)
    await create(db, project, {"owner": graph.user, **PROJECT_FIELDS})
    await relate(
        db,
        "includes",
        project,
        graph.nodes["sense"],
        {"owner": graph.user, "hidden": False, "added_at": NOW},
    )
    assert (await graph.get(client, "sense", depth=0)).status_code == 200
    # A lexeme marker hides its senses even when the lemma itself remains visible.
    await db.update(graph.memberships["lemma"]).merge({"hidden": False})
    marker = await relate(
        db,
        "includes",
        graph.project,
        graph.nodes["lexeme"],
        {"owner": graph.user, "hidden": True, "added_at": NOW},
    )
    assert marker["hidden"]
    assert (await graph.get(client, "lemma", depth=0)).status_code == 200
    assert (await graph.get(client, "lexeme", depth=0)).status_code == 404


async def test_auth_validation_and_foreign_focus(graph: Fixture, client: AsyncClient) -> None:
    url = "/api/graph"
    assert (await client.get(url, params={"focus_id": "bad"})).status_code == 401
    for params in [
        {"focus_id": "lemma:raw"},
        {"focus_id": "%%%"},
        {"depth": 4},
        {"depth": -1},
        {"node_types": ["user"]},
        {"relation_types": ["includes"]},
        {"direction": "sideways"},
        {"node_types": ["sense"]},
    ]:
        assert (await graph.get(client, **params)).status_code == 422
    response = await client.get(
        url,
        headers=graph.other_headers,
        params={"focus_id": encode_rid(graph.nodes["lemma"], "lemma")},
    )
    assert response.status_code == 404
    private = await client.get(
        url,
        headers=graph.other_headers,
        params={"focus_id": encode_rid(graph.nodes["tag"], "tag")},
    )
    assert private.status_code == 404
    missing = encode_rid(RecordID("tag", uuid4().hex), "tag")
    assert (await graph.get(client, focus_id=missing)).status_code == 404


async def test_no_unselected_shared_or_foreign_edges_and_endpoints(
    graph: Fixture, client: AsyncClient, db: AsyncWsSurrealConnection
) -> None:
    baseline = (await graph.get(client, "sense", depth=3)).json()
    for owner in (None, graph.other):
        private = RecordID("tag", uuid4().hex)
        content: dict[str, Any] = {"kind": "custom", "name": "Unauthorized"}
        if owner is not None:
            content["owner"] = owner
        await create(db, private, content)
        await relate(db, "member_of", graph.nodes["sense"], private, {"owner": graph.user})
    # Independently foreign edges between authorized endpoints must also disappear.
    await relate(
        db,
        "relates_to",
        graph.nodes["sense"],
        graph.nodes["sense2"],
        {"owner": graph.other, "type": "antonym", "source": "custom"},
    )
    assert (await graph.get(client, "sense", depth=3)).json() == baseline
    # Shared edges are authorized, but only when both endpoint selections exist.
    shared = await relate(db, "member_of", graph.nodes["morpheme"], graph.nodes["tag"], {})
    response = (await graph.get(client, "morpheme", depth=1)).json()
    assert encode_rid(shared["id"], "member_of") in {edge["id"] for edge in response["edges"]}
