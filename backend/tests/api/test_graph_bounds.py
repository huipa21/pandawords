from typing import Any

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import encode_rid
from app.db import graph_visibility
from app.db.dictionary_schema_test_support import relate
from app.db.graph_test_support import tags
from app.domain.identity import user_key
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("dense", [False, True])
async def test_hard_node_and_dense_edge_bounds(
    dense: bool,
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = await make_user()
    user = RecordID("user", user_key(alice.id))
    headers = bearer(await login(client, alice.username))
    records = await tags(db, user, 101 if dense else 300, dense=dense)
    original = graph_visibility._rows
    sizes: list[int] = []

    async def measured(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        rows = await original(*args, **kwargs)
        sizes.append(len(rows))
        return rows

    monkeypatch.setattr(graph_visibility, "_rows", measured)
    params = {"focus_id": encode_rid(records[0], "tag"), "depth": 3}
    response = await client.get("/api/graph", headers=headers, params=params)
    if not dense:
        assert response.status_code == 200, response.text
        assert len(response.json()["nodes"]) == 300
        assert len(response.json()["edges"]) == 299
        extra = (await tags(db, user, 1))[0]
        await relate(db, "member_of", records[0], extra, {"owner": user})
        assert len(sizes) <= 55
        sizes.clear()
        response = await client.get("/api/graph", headers=headers, params=params)
    assert response.status_code == 413, response.text
    assert response.json()["code"] == "graph.too_large"
    assert "Reduce depth" in response.json()["message"]
    assert "nodes" not in response.json() and "edges" not in response.json()
    assert len(sizes) <= 55
    assert max(sizes) <= 10_001
    assert sum(sizes) <= 31_000
    reduced = await client.get("/api/graph", headers=headers, params={**params, "depth": 0})
    assert reduced.status_code == 200, reduced.text
    assert len(reduced.json()["nodes"]) == 1
