"""Owner-bound mutations used only by real-database scheduling tests."""

from datetime import UTC, datetime
from uuid import uuid4

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.record_ids import decode_rid
from app.db.auth import _rows
from app.db.srs import user_record
from app.domain.srs import MemoryRead


async def remove_memory(db: AsyncSurrealConnection, owner: str, memory: MemoryRead) -> None:
    await _rows(
        db,
        "DELETE $memory WHERE owner = $user;",
        {"memory": decode_rid(memory.id, "memory"), "user": user_record(owner)},
    )


async def change_owner(
    db: AsyncSurrealConnection,
    target: RecordID,
    old_owner: RecordID | None,
    new_owner: RecordID | None,
) -> None:
    await _rows(
        db,
        "UPDATE $target SET owner = $new WHERE owner = $old RETURN AFTER;",
        {"target": target, "old": old_owner, "new": new_owner},
    )


async def seed_history(
    db: AsyncSurrealConnection,
    owner: str,
    memory: MemoryRead,
    project: str,
    exercise: str,
    durations: list[int],
    *,
    correct: bool = True,
    at: datetime | None = None,
    introduction: bool = False,
) -> None:
    for duration in durations:
        await _rows(
            db,
            "CREATE $log CONTENT $content;",
            {
                "log": RecordID("review_log", uuid4().hex),
                "content": {
                    "owner": user_record(owner),
                    "memory": decode_rid(memory.id, "memory"),
                    "project": decode_rid(project, "project"),
                    "exercise": exercise,
                    "rating": 3,
                    "auto_rating": 3,
                    "correct": correct,
                    "hint_used": False,
                    "duration_ms": duration,
                    "at": at or datetime.now(UTC),
                    "is_introduction": introduction,
                    "attempt_id": uuid4().hex,
                },
            },
        )
