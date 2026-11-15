"""Transaction-scoped preference and restore-receipt access for user restore (6.1.4).

Only ``prefs``, ``source_lang`` and ``target_lang`` of the authenticated user are read or
written; username, role, password hash, flags and tokens are never touched.
"""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.db.auth import _rows
from app.domain.user_backup import PreferenceMerge


def _receipt_id(user: RecordID, bundle: str) -> RecordID:
    return RecordID("restore_receipt", [user, bundle])


async def read_receipt(
    db: AsyncSurrealConnection, user: RecordID, bundle: str, txn: UUID | None = None
) -> dict[str, Any] | None:
    """The stored summary of an earlier restore of this backup while its result still exists.

    A receipt whose restored projects were all deleted since no longer blocks a new restore.
    """
    rows = await _rows(
        db,
        "SELECT projects, summary FROM $id WHERE owner = $user;",
        {"id": _receipt_id(user, bundle), "user": user},
        txn_id=txn,
    )
    if not rows:
        return None
    projects = cast(list[RecordID], rows[0]["projects"])
    if projects:
        alive = await _rows(
            db,
            "SELECT id FROM $projects WHERE owner = $user;",
            {"projects": cast(Value, projects), "user": user},
            txn_id=txn,
        )
        if not alive:
            return None
    return cast(dict[str, Any], rows[0]["summary"])


async def read_account(db: AsyncSurrealConnection, user: RecordID, txn: UUID) -> dict[str, Any]:
    rows = await _rows(
        db,
        "SELECT prefs, source_lang, target_lang FROM $user WHERE id = $user;",
        {"user": user},
        txn_id=txn,
    )
    return rows[0] if rows else {}


async def write_preferences(
    db: AsyncSurrealConnection, user: RecordID, merge: PreferenceMerge, txn: UUID
) -> None:
    if not merge.restored:
        return
    current = await read_account(db, user, txn)
    await _rows(
        db,
        "UPDATE $user SET prefs = $prefs, source_lang = $source, target_lang = $target "
        "WHERE id = $user RETURN NONE;",
        {
            "user": user,
            "prefs": cast(Value, merge.prefs),
            "source": merge.langs.get("source_lang", current.get("source_lang")),
            "target": merge.langs.get("target_lang", current.get("target_lang")),
        },
        txn_id=txn,
    )


async def write_receipt(
    db: AsyncSurrealConnection,
    user: RecordID,
    bundle: str,
    projects: list[RecordID],
    summary: dict[str, Any],
    txn: UUID,
) -> None:
    await _rows(
        db,
        "UPSERT $id CONTENT $content RETURN NONE;",
        {
            "id": _receipt_id(user, bundle),
            "content": cast(
                Value,
                {
                    "owner": user,
                    "bundle": bundle,
                    "restored_at": datetime.now(UTC),
                    "projects": projects,
                    "summary": summary,
                },
            ),
        },
        txn_id=txn,
    )
