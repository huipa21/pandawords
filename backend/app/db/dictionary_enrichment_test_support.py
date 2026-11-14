"""Bound shared-record setup for isolated enrichment regressions."""

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value


async def reset_metadata(
    db: AsyncSurrealConnection, lemma: RecordID, fields: dict[str, Value]
) -> None:
    await db.query(
        "UPDATE $record MERGE $fields WHERE owner = NONE;", {"record": lemma, "fields": fields}
    )


async def clear_edges(db: AsyncSurrealConnection) -> None:
    await db.query("DELETE relates_to WHERE owner = NONE; DELETE derives_to WHERE owner = NONE;")
