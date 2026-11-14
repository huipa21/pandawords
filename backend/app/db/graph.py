"""Owner-safe bounded breadth-first graph snapshot; no per-node database calls."""

from typing import Any, cast, get_args
from uuid import UUID

from pydantic import TypeAdapter
from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic
from app.db.dictionary import RELATIONS, TABLE_FIELDS, _json, _merge
from app.db.graph_visibility import MAX_EDGE_ROWS, bounded_rows, too_large, visible
from app.domain.dictionary import DictionaryRelation, DictionaryTable
from app.domain.graph import GraphEdge, GraphNode, GraphQuery, GraphRead, GraphSeedsQuery
from app.domain.identity import user_key

NODE_LIMIT = 300
_node = TypeAdapter(GraphNode)


async def seeds(
    db: AsyncSurrealConnection, owner: str, query: GraphSeedsQuery, project: RecordID | None
) -> list[GraphNode]:
    async def operation(txn: UUID) -> list[GraphNode]:
        user = RecordID("user", user_key(owner))
        authorized = await visible(db, user, txn, project)
        # Fetch in bounded batches to apply effective overrides before text matching.
        records = sorted(authorized, key=str)
        matches: list[GraphNode] = []
        start = (query.page - 1) * query.page_size
        for offset in range(0, len(records), NODE_LIMIT):
            nodes = await _nodes(db, user, set(records[offset : offset + NODE_LIMIT]), txn)
            for node in nodes:
                fields = node.fields.model_dump(by_alias=True)
                label = next(
                    (
                        fields[key]
                        for key in ("text", "definition", "name", "title", "pos")
                        if isinstance(fields.get(key), str)
                    ),
                    "",
                )
                if query.q.casefold() in label.casefold():
                    matches.append(node)
            if len(matches) >= start + query.page_size:
                break
        return matches[start : start + query.page_size]

    return await _atomic(db, operation)


async def _edges(
    db: AsyncSurrealConnection,
    user: RecordID,
    frontier: set[RecordID],
    authorized: set[RecordID],
    relations: list[DictionaryRelation],
    direction: str,
    txn: UUID,
    *,
    induced: bool = False,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for table in relations:
        rows = await bounded_rows(
            db,
            "SELECT * FROM type::table($table) WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user) "
            "AND in IN $authorized AND out IN $authorized "
            "AND (($induced AND in IN $frontier AND out IN $frontier) OR "
            "($induced = false AND (($direction != 'incoming' AND in IN $frontier) OR "
            "($direction != 'outgoing' AND out IN $frontier)))) LIMIT $limit;",
            {
                "table": table,
                "user": user,
                "frontier": cast(Value, list(frontier)),
                "authorized": cast(Value, list(authorized)),
                "direction": direction,
                "induced": induced,
            },
            txn,
            MAX_EDGE_ROWS - len(result),
        )
        result.extend(rows)
    return result


async def _nodes(
    db: AsyncSurrealConnection, user: RecordID, selected: set[RecordID], txn: UUID
) -> list[GraphNode]:
    overlays_ids = cast(Value, [RecordID("override", [user, record]) for record in selected])
    overlays = await bounded_rows(
        db,
        "SELECT id, fields FROM $targets WHERE owner = $user LIMIT $limit;",
        {"user": user, "targets": overlays_ids},
        txn,
        NODE_LIMIT,
    )
    changes = {row["id"].id[1]: row["fields"] for row in overlays}
    result: list[GraphNode] = []
    for table, allowed in TABLE_FIELDS.items():
        ids = [record for record in selected if record.table_name == table]
        if not ids:
            continue
        rows = await bounded_rows(
            db,
            "SELECT * FROM $targets WHERE owner = NONE OR owner = $user LIMIT $limit;",
            {"user": user, "targets": cast(Value, ids)},
            txn,
            NODE_LIMIT,
        )
        for row in rows:
            record = row["id"]
            fields = {key: value for key, value in row.items() if key in allowed}
            fields = _merge(
                fields,
                {key: value for key, value in changes.get(record, {}).items() if key in allowed},
            )
            result.append(
                _node.validate_python(
                    {"id": encode_rid(record, table), "table": table, "fields": _json(fields)}
                )
            )
    return sorted(result, key=lambda node: (node.table, node.id))


async def read(
    db: AsyncSurrealConnection, owner: str, focus: RecordID, query: GraphQuery
) -> GraphRead:
    async def operation(txn: UUID) -> GraphRead:
        user = RecordID("user", user_key(owner))
        authorized = await visible(db, user, txn)
        if focus not in authorized:
            raise AppError("graph.not_found", 404, "Graph focus not found.")
        types = sorted(set(query.node_types or get_args(DictionaryTable.__value__)))
        relations = sorted(set(query.relation_types or RELATIONS))
        if focus.table_name not in types:
            raise AppError("graph.focus_filtered", 422, "Node filters must include the focus type.")
        authorized = {record for record in authorized if record.table_name in types}
        selected, frontier = {focus}, {focus}
        for _ in range(query.depth):
            edges = await _edges(db, user, frontier, authorized, relations, query.direction, txn)
            adjacent = {edge[end] for edge in edges for end in ("in", "out")}
            frontier = adjacent - selected
            selected.update(frontier)
            if len(selected) > NODE_LIMIT:
                raise too_large()
            if not frontier:
                break
        rows = await _edges(
            db, user, selected, selected, relations, query.direction, txn, induced=True
        )
        edge_fields = {"rank", "order", "position", "via", "type", "source", "span"}
        edges = [
            GraphEdge.model_validate(
                {
                    "id": encode_rid(row["id"], row["id"].table_name),
                    "table": row["id"].table_name,
                    "start": encode_rid(row["in"], row["in"].table_name),
                    "end": encode_rid(row["out"], row["out"].table_name),
                    "fields": _json(
                        {key: value for key, value in row.items() if key in edge_fields}
                    ),
                }
            )
            for row in rows
        ]
        return GraphRead(
            focus_id=query.focus_id,
            depth=query.depth,
            direction=query.direction,
            nodes=await _nodes(db, user, selected, txn),
            edges=sorted(edges, key=lambda edge: (edge.table, edge.start, edge.end, edge.id)),
            node_types=cast(list[DictionaryTable], types),
            relation_types=relations,
        )

    return await _atomic(db, operation)
