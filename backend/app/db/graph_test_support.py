"""Bound-parameter dense fixtures for real graph query regression tests."""

from typing import Any, cast
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.graph_visibility import MAX_EDGE_ROWS, bounded_rows
from app.db.migration_store import checked_query
from app.domain.dictionary import DictionaryRelation


async def legacy_edges(
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
    """Pre-7.1.4 oracle retained for exact-output and timing comparisons."""
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


async def tags(
    db: AsyncWsSurrealConnection, user: RecordID, count: int, *, dense: bool = False
) -> list[RecordID]:
    records = [RecordID("tag", uuid4().hex) for _ in range(count)]
    await checked_query(
        db,
        "FOR $record IN $records { CREATE $record CONTENT "
        "{owner: $user, kind: 'custom', name: 'Bounded fixture'}; };",
        {"records": cast(Value, records), "user": user},
    )
    starts = records if dense else records[:1]
    for offset in range(0, len(starts), 5):
        await checked_query(
            db,
            "FOR $start IN $starts { FOR $target IN $targets { "
            "RELATE $start->member_of->$target CONTENT {owner: $user}; }; };",
            {
                "starts": cast(Value, starts[offset : offset + 5]),
                "targets": cast(Value, records if dense else records[1:]),
                "user": user,
            },
        )
    return records
