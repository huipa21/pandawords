"""Owner-scoped cards, preferences and transaction-aware completed review storage."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from fsrs import Card
from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _rows
from app.db.project_tree import _children, _hidden, _memberships
from app.domain.identity import user_key
from app.domain.srs import CardState, MemoryRead, SrsPreferences


def user_record(owner: str) -> RecordID:
    return RecordID("user", user_key(owner))


def memory_read(row: dict[str, Any]) -> MemoryRead:
    return MemoryRead(
        id=encode_rid(row["id"], "memory"),
        sense_id=encode_rid(row["sense"], "sense"),
        introduced=row["introduced"],
        card=CardState.model_validate({key: row.get(key) for key in CardState.model_fields}),
    )


async def read_memory(
    db: AsyncSurrealConnection, owner: str, sense: RecordID, txn: UUID | None = None
) -> MemoryRead | None:
    user = user_record(owner)
    rows = await _rows(
        db,
        "SELECT * FROM $memory WHERE owner = $user;",
        {"memory": RecordID("memory", [user, sense]), "user": user},
        txn_id=txn,
    )
    return memory_read(rows[0]) if rows else None


async def ensure_memory(db: AsyncSurrealConnection, owner: str, sense: RecordID, txn: UUID) -> bool:
    user = user_record(owner)
    if not await _rows(
        db,
        "SELECT id FROM $sense WHERE owner = NONE OR owner = $user;",
        {"sense": sense, "user": user},
        txn_id=txn,
    ):
        raise AppError("srs.not_found", 404, "Sense not found.")
    if await read_memory(db, owner, sense, txn):
        return False
    card = CardState.from_card(Card())
    await _rows(
        db,
        "CREATE $memory CONTENT $content;",
        {
            "memory": RecordID("memory", [user, sense]),
            "content": cast(
                Value, {"owner": user, "sense": sense, "introduced": False, **card.model_dump()}
            ),
        },
        txn_id=txn,
    )
    return True


async def selected_senses(db: AsyncSurrealConnection, owner: str, txn: UUID) -> list[RecordID]:
    rows = await _rows(
        db,
        "SELECT out FROM includes WHERE owner = $user AND in.owner = $user "
        "AND record::tb(out) = 'sense' AND (out.owner = NONE OR out.owner = $user);",
        {"user": user_record(owner)},
        txn_id=txn,
    )
    return list({row["out"] for row in rows})


async def eligible_project(
    db: AsyncSurrealConnection, owner: str, project: RecordID, sense: RecordID, txn: UUID
) -> dict[str, Any]:
    user = user_record(owner)
    memberships = await _memberships(db, user, project, txn)
    flags = _hidden(memberships)
    sense_key = encode_rid(sense, "sense")
    if sense_key in flags and not flags[sense_key]:
        for row in memberships:
            lemma = row["out"]
            if lemma.table_name != "lemma" or flags[encode_rid(lemma, "lemma")]:
                continue
            for edge in await _children(db, user, lemma, "has_lexeme", None, txn):
                lexeme = edge["out"]
                if flags.get(encode_rid(lexeme, "lexeme"), False):
                    continue
                if await _children(db, user, lexeme, "has_sense", [sense], txn):
                    rows = await _rows(
                        db,
                        "SELECT * FROM $project WHERE owner = $user;",
                        {"project": project, "user": user},
                        txn_id=txn,
                    )
                    return rows[0]
    raise AppError("srs.not_eligible", 409, "Sense is not visible in this project.")


async def preferences(
    db: AsyncSurrealConnection,
    owner: str,
    txn: UUID | None = None,
    update: SrsPreferences | None = None,
) -> SrsPreferences:
    parameters: dict[str, Value] = {"user": user_record(owner)}
    if update is None:
        query = "SELECT prefs FROM $user WHERE id = $user;"
    else:
        query = (
            "UPDATE $user SET prefs.desired_retention = $retention WHERE id = $user RETURN AFTER;"
        )
        parameters["retention"] = update.desired_retention
    rows = await _rows(db, query, parameters, txn_id=txn)
    if not rows:
        raise AppError("auth.user_not_found", 404, "User not found.")
    return SrsPreferences(desired_retention=rows[0]["prefs"].get("desired_retention", 0.9))


async def prior_correct(
    db: AsyncSurrealConnection, owner: str, exercise: str, txn: UUID
) -> list[int]:
    rows = await _rows(
        db,
        "SELECT duration_ms, at, id FROM review_log WHERE owner = $user "
        "AND exercise = $exercise AND correct = true ORDER BY at DESC, id DESC LIMIT 100;",
        {"user": user_record(owner), "exercise": exercise},
        txn_id=txn,
    )
    return [row["duration_ms"] for row in rows]


async def completed(
    db: AsyncSurrealConnection, owner: str, attempt_id: str, txn: UUID
) -> dict[str, Any] | None:
    rows = await _rows(
        db,
        "SELECT * FROM review_log WHERE owner = $user AND attempt_id = $attempt;",
        {"user": user_record(owner), "attempt": attempt_id},
        txn_id=txn,
    )
    return rows[0] if rows else None


async def check_daily_limit(
    db: AsyncSurrealConnection,
    owner: str,
    project: dict[str, Any],
    introduction: bool,
    now: datetime,
    txn: UUID,
) -> None:
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await _rows(
        db,
        "SELECT count() AS total FROM review_log WHERE owner = $user "
        "AND project = $project AND at >= $start AND at < $end "
        "AND is_introduction = $introduction GROUP ALL;",
        {
            "user": user_record(owner),
            "project": project["id"],
            "start": start,
            "end": start + timedelta(days=1),
            "introduction": introduction,
        },
        txn_id=txn,
    )
    count = rows[0]["total"] if rows else 0
    limit = project["plan"].get("daily_new" if introduction else "review_cap")
    if limit is not None and count >= limit:
        raise AppError("srs.daily_limit", 409, "The project's daily limit has been reached.")
    # Serialize reviews of different cards against the same project cap.
    await _rows(
        db,
        "UPDATE $project SET srs_revision += 1 WHERE owner = $user RETURN AFTER;",
        {
            "project": project["id"],
            "user": user_record(owner),
        },
        txn_id=txn,
    )


async def save_review(
    db: AsyncSurrealConnection,
    owner: str,
    sense: RecordID,
    card: CardState,
    log: dict[str, Any],
    txn: UUID,
) -> None:
    user = user_record(owner)
    await _rows(
        db,
        "UPDATE $memory MERGE $content WHERE owner = $user RETURN AFTER;",
        {
            "memory": RecordID("memory", [user, sense]),
            "user": user,
            "content": cast(Value, {**card.model_dump(), "introduced": True}),
        },
        txn_id=txn,
    )
    await _rows(
        db,
        "CREATE $log CONTENT $content;",
        {"log": RecordID("review_log", uuid4().hex), "content": cast(Value, log)},
        txn_id=txn,
    )
