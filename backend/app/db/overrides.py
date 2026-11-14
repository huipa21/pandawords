from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.db.dictionary import _merge
from app.db.user_dictionary import require_visible
from app.domain.dictionary import DictionaryTable
from app.domain.identity import user_key
from app.domain.overrides import OverrideFields, OverrideRead


async def manage(
    db: AsyncSurrealConnection,
    owner: str,
    target: RecordID,
    *,
    action: Literal["get", "put", "patch", "delete"],
    fields: dict[str, Any] | None = None,
) -> OverrideRead | None:
    async def operation(txn: UUID) -> OverrideRead | None:
        user = RecordID("user", user_key(owner))
        await require_visible(db, user, target, txn)
        overlay = RecordID("override", [user, target])
        params: dict[str, Value] = {"overlay": overlay, "user": user}
        rows = await _rows(db, "SELECT * FROM $overlay WHERE owner = $user;", params, txn_id=txn)
        if action == "delete":
            await _rows(
                db, "DELETE $overlay WHERE owner = $user RETURN BEFORE;", params, txn_id=txn
            )
            return None
        if action in {"put", "patch"}:
            changes = fields or {}
            if action == "patch" and rows:
                changes = _merge(rows[0]["fields"], changes)
            # A corrupt deterministic ID must never let one user overwrite another's row.
            if rows:
                rows = await _rows(
                    db,
                    "UPDATE $overlay SET fields = $fields, updated_at = $now "
                    "WHERE owner = $user RETURN AFTER;",
                    {
                        **params,
                        "fields": changes,
                        "now": datetime.now(UTC),
                    },
                    txn_id=txn,
                )
            else:
                rows = await _rows(
                    db,
                    "CREATE $overlay CONTENT $content RETURN AFTER;",
                    {
                        **params,
                        "content": {
                            "owner": user,
                            "fields": changes,
                            "updated_at": datetime.now(UTC),
                        },
                    },
                    txn_id=txn,
                )
        if not rows:
            raise AppError("override.not_found", 404, "Override not found.")
        return OverrideRead(
            target_table=cast(DictionaryTable, target.table_name),
            target_id=encode_rid(target, target.table_name),
            fields=OverrideFields.model_validate(rows[0]["fields"]),
            updated_at=rows[0]["updated_at"],
        )

    return await _atomic(db, operation)
