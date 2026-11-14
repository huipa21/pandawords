"""Owner-bound schedule and migration probes for the real planning tests."""

from datetime import datetime

from surrealdb import AsyncSurrealConnection

from app.core.record_ids import decode_rid
from app.db.auth import _rows
from app.db.srs import user_record
from app.domain.srs import MemoryRead


async def schedule(
    db: AsyncSurrealConnection,
    owner: str,
    memory: MemoryRead,
    due: datetime,
    *,
    stability: float | None = 10,
    last_review: datetime | None = None,
) -> None:
    await _rows(
        db,
        "UPDATE $memory SET introduced = true, state = 2, step = NONE, due = $due, "
        "stability = $stability, difficulty = 5.0, last_review = $last WHERE owner = $user;",
        {
            "memory": decode_rid(memory.id, "memory"),
            "user": user_record(owner),
            "due": due,
            "stability": stability,
            "last": last_review,
        },
    )
