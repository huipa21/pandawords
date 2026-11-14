"""Visibility checks and atomic user-owned dictionary extensions."""

from typing import Any
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.domain.dictionary import DictionaryRecordRead
from app.domain.identity import user_key
from app.domain.overrides import EDITABLE_FIELDS
from app.domain.user_dictionary import CustomSenseCreate


def not_found() -> AppError:
    return AppError("dictionary.not_found", 404, "Dictionary item not found.")


async def require_visible(
    db: AsyncSurrealConnection, user: RecordID, target: RecordID, txn: UUID
) -> dict[str, Any]:
    if target.table_name not in EDITABLE_FIELDS:
        raise not_found()
    rows = await _rows(
        db,
        "SELECT * FROM $target WHERE owner = NONE OR owner = $user;",
        {"target": target, "user": user},
        txn_id=txn,
    )
    if not rows:
        raise not_found()
    return rows[0]


async def create_sense(
    db: AsyncSurrealConnection, owner: str, lexeme: RecordID, data: CustomSenseCreate
) -> DictionaryRecordRead:
    async def operation(txn: UUID) -> DictionaryRecordRead:
        user = RecordID("user", user_key(owner))
        await require_visible(db, user, lexeme, txn)
        sense = RecordID("sense", uuid4().hex)
        fields = {**data.model_dump(), "source": "custom"}
        await _rows(
            db,
            "CREATE $sense CONTENT $content;",
            {"sense": sense, "content": {**fields, "owner": user}},
            txn_id=txn,
        )
        await _rows(
            db,
            "RELATE $lexeme->$edge->$sense CONTENT $content;",
            {
                "lexeme": lexeme,
                "edge": RecordID("has_sense", uuid4().hex),
                "sense": sense,
                "content": {"owner": user, "rank": data.rank},
            },
            txn_id=txn,
        )
        return DictionaryRecordRead(
            id=encode_rid(sense, "sense"), table="sense", owner=owner, fields=fields
        )

    return await _atomic(db, operation)
