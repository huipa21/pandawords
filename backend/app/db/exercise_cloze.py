"""Bounded private contexts; never write sentence text to shared exercise caches."""

from dataclasses import dataclass
from uuid import UUID

from surrealdb import AsyncSurrealConnection

from app.core.record_ids import decode_rid
from app.db.auth import _atomic, _rows
from app.db.srs import user_record
from app.domain.exercises import ExerciseContext

LIMIT = 64


@dataclass(frozen=True)
class SentenceContext:
    text: str
    spans: tuple[tuple[int, int], ...]


async def sentences(
    db: AsyncSurrealConnection, context: ExerciseContext
) -> tuple[SentenceContext, ...]:
    async def operation(txn: UUID) -> tuple[SentenceContext, ...]:
        params = {
            "user": user_record(context.owner),
            "sense": decode_rid(context.sense_id, "sense"),
            "project": decode_rid(context.project_id, "project"),
            "limit": LIMIT + 1,
        }
        hidden = await _rows(
            db,
            "SELECT out FROM includes WHERE owner = $user AND in = $project "
            "AND in.owner = $user AND hidden = true ORDER BY out LIMIT $limit;",
            params,
            txn_id=txn,
        )
        if len(hidden) > LIMIT:
            return ()
        rows = await _rows(
            db,
            "SELECT id, out, out.text AS text, span FROM used_in "
            "WHERE owner = $user AND in = $sense AND in.id != NONE "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND out.owner = $user AND out.id != NONE AND out.lang = 'en' "
            "AND record::tb(out) = 'sentence' AND out NOT IN $hidden "
            "ORDER BY out, id LIMIT $limit;",
            {**params, "hidden": [row["out"] for row in hidden]},
            txn_id=txn,
        )
        # A partial sentence may omit confirmed occurrences. Fail closed instead.
        if len(rows) > LIMIT:
            return ()
        grouped: dict[str, tuple[str, list[tuple[int, int]]]] = {}
        for row in rows:
            span = row.get("span")
            if not isinstance(span, list) or len(span) != 2:
                continue
            text = row.get("text")
            if not isinstance(text, str):
                continue
            _, spans = grouped.setdefault(str(row["out"]), (text, []))
            spans.append((span[0], span[1]))
        return tuple(SentenceContext(text, tuple(spans)) for text, spans in grouped.values())

    return await _atomic(db, operation)
