"""Reproduce the pre-change and current graph costs against isolated real databases."""

import json
import math
import platform
import statistics
from collections import Counter
from time import perf_counter
from typing import Any
from uuid import uuid4

import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db import graph, graph_visibility
from app.db.auth import _atomic
from app.db.graph_perf_support import Workload, edge_query_plans, workload
from app.db.graph_test_support import legacy_edges, tags
from app.domain.auth import UserCreate
from app.domain.graph import GraphQuery, GraphRead
from app.domain.identity import user_key
from app.services.auth import create_user

pytestmark = pytest.mark.integration
SAMPLES = 40


def summary(durations: list[float], counts: list[int]) -> dict[str, Any]:
    ordered = sorted(durations)
    return {
        "queries": sorted(set(counts)),
        "min_ms": round(ordered[0], 2),
        "median_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 2),
        "max_ms": round(ordered[-1], 2),
    }


def outline(plan: Any) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                visit(child)
        elif isinstance(node, dict):
            attributes = node.get("attributes", {})
            if "operator" in node:
                item: dict[str, Any] = {"keys": sorted(node.keys())}
                for key in ("name", "operation", "operator", "kind", "type"):
                    value = node.get(key)
                    if isinstance(value, str) and len(value) < 100:
                        item[key] = value
                if isinstance(attributes, dict):
                    item["attribute_keys"] = sorted(attributes.keys())
                    for key in ("table", "index", "source", "limit", "count", "rows"):
                        value = attributes.get(key)
                        if isinstance(value, str | int) and len(str(value)) < 100:
                            item[key] = value
                counts[json.dumps(item, sort_keys=True)] += 1
            visit(node.get("children", []))

    visit(plan)
    return [{**json.loads(item), "occurrences": count} for item, count in counts.items()]


def assert_fixture(result: GraphRead, fixture: Workload) -> None:
    nodes = [node.id for node in result.nodes]
    edges = [edge.id for edge in result.edges]
    assert set(nodes) == {encode_rid(record, record.table_name) for record in fixture.nodes}
    assert set(edges) == {encode_rid(record, record.table_name) for record in fixture.edges}
    assert not set(nodes) & {
        encode_rid(record, record.table_name) for record in fixture.excluded_nodes
    }
    assert not set(edges) & {
        encode_rid(record, record.table_name) for record in fixture.excluded_edges
    }
    assert result.nodes == sorted(result.nodes, key=lambda node: (node.table, node.id))
    assert result.edges == sorted(
        result.edges, key=lambda edge: (edge.table, edge.start, edge.end, edge.id)
    )


@pytest.mark.parametrize("size", [30, 300])
async def test_graph_workload(
    size: int, job_db: AsyncWsSurrealConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = job_db
    alice = await create_user(
        db, UserCreate(username=f"perf_{uuid4().hex}", password="test-password")
    )
    bob = await create_user(
        db, UserCreate(username=f"perf_{uuid4().hex}", password="test-password")
    )
    user, other = RecordID("user", user_key(alice.id)), RecordID("user", user_key(bob.id))
    fixture = await workload(db, user, other, size)
    await tags(db, other, 300)
    if size == 300:
        await tags(db, other, 50, dense=True)
    focus = fixture.nodes[0]
    focus_id = encode_rid(focus, "lemma")
    query = GraphQuery(focus_id=focus_id, depth=3)
    variants = [
        query,
        GraphQuery(focus_id=focus_id, depth=3, direction="outgoing"),
        GraphQuery(focus_id=focus_id, depth=3, direction="incoming"),
        GraphQuery(focus_id=focus_id, depth=0),
        GraphQuery(focus_id=focus_id, depth=3, relation_types=["has_lexeme"]),
        GraphQuery(focus_id=focus_id, depth=3, node_types=["lemma", "lexeme"]),
    ]
    optimized = graph._edges
    reference: GraphRead | None = None
    filtered_reference: GraphRead | None = None
    for variant in variants:
        monkeypatch.setattr(graph, "_edges", legacy_edges)
        expected = await graph.read(db, alice.id, focus, variant)
        monkeypatch.setattr(graph, "_edges", optimized)
        actual = await graph.read(db, alice.id, focus, variant)
        assert actual == expected
        if variant == query:
            reference = expected
            assert_fixture(actual, fixture)
        if variant.relation_types == ["has_lexeme"]:
            filtered_reference = expected
    assert reference is not None
    assert filtered_reference is not None
    with pytest.raises(AppError) as denied:
        await graph.read(db, bob.id, focus, query)
    assert denied.value.code == "graph.not_found"

    original_rows = graph_visibility._rows
    query_count = 0

    async def counted(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        nonlocal query_count
        query_count += 1
        return await original_rows(*args, **kwargs)

    monkeypatch.setattr(graph_visibility, "_rows", counted)
    durations: dict[str, list[float]] = {"baseline": [], "optimized": []}
    counts: dict[str, list[int]] = {"baseline": [], "optimized": []}
    implementations = (("baseline", legacy_edges), ("optimized", optimized))
    for sample in range(SAMPLES):
        order = implementations if sample % 2 == 0 else implementations[::-1]
        for label, implementation in order:
            monkeypatch.setattr(graph, "_edges", implementation)
            query_count = 0
            start = perf_counter()
            result = await graph.read(db, alice.id, focus, query)
            durations[label].append((perf_counter() - start) * 1000)
            counts[label].append(query_count)
            assert result == reference
    filtered: dict[str, dict[str, Any]] = {}
    if size == 300:
        filtered_query = GraphQuery(focus_id=focus_id, depth=3, relation_types=["has_lexeme"])
        filtered_durations: dict[str, list[float]] = {"baseline": [], "optimized": []}
        filtered_counts: dict[str, list[int]] = {"baseline": [], "optimized": []}
        for sample in range(SAMPLES):
            order = implementations if sample % 2 == 0 else implementations[::-1]
            for label, implementation in order:
                monkeypatch.setattr(graph, "_edges", implementation)
                query_count = 0
                start = perf_counter()
                result = await graph.read(db, alice.id, focus, filtered_query)
                filtered_durations[label].append((perf_counter() - start) * 1000)
                filtered_counts[label].append(query_count)
                assert result == filtered_reference
        filtered = {
            label: summary(filtered_durations[label], filtered_counts[label])
            for label in ("baseline", "optimized")
        }
    monkeypatch.setattr(graph, "_edges", optimized)
    plans = await _atomic(db, lambda txn: edge_query_plans(db, user, set(fixture.nodes), txn))
    filtered_plans = await _atomic(
        db, lambda txn: edge_query_plans(db, user, set(fixture.nodes), txn, filtered=True)
    )
    baseline = summary(durations["baseline"], counts["baseline"])
    after = summary(durations["optimized"], counts["optimized"])
    print(
        json.dumps(
            {
                "size": size,
                "edges": len(fixture.edges),
                "depth": 3,
                "samples_per_version": SAMPLES,
                "filtered_samples_per_version": SAMPLES if filtered else 0,
                "python": platform.python_version(),
                "baseline": baseline,
                "optimized": after,
                "filtered": filtered,
                "plans": {label: outline(plan) for label, plan in plans.items()},
                "filtered_plans": {label: outline(plan) for label, plan in filtered_plans.items()},
            },
            default=str,
        )
    )
    assert max(counts["optimized"]) <= 22
    assert after["p95_ms"] < 2000
