"""Canonical, minimal target context; never include private overlays or notes."""

from typing import Any
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError
from app.db.auth import _atomic, _rows
from app.db.user_dictionary import require_visible
from app.domain.identity import user_key


async def context(db: AsyncSurrealConnection, owner: str, target: RecordID) -> dict[str, Any]:
    async def operation(txn: UUID) -> dict[str, Any]:
        user = RecordID("user", user_key(owner))
        row = await require_visible(db, user, target, txn)
        fields = {
            "lemma": ("text",),
            "lexeme": ("pos", "forms"),
            "sense": ("definition", "gloss"),
        }[target.table_name]
        result = {field: row.get(field) for field in fields}
        child = target
        relations = (
            ("has_sense", "has_lexeme")
            if target.table_name == "sense"
            else ("has_lexeme",)
            if target.table_name == "lexeme"
            else ()
        )
        for relation in relations:
            query = {
                "has_sense": "SELECT in FROM has_sense WHERE out = $target "
                "AND (owner = NONE OR owner = $user) ORDER BY id;",
                "has_lexeme": "SELECT in FROM has_lexeme WHERE out = $target "
                "AND (owner = NONE OR owner = $user) ORDER BY id;",
            }[relation]
            edges = await _rows(db, query, {"target": child, "user": user}, txn_id=txn)
            for edge in edges:
                parent = edge["in"]
                try:
                    ancestor = await require_visible(db, user, parent, txn)
                except AppError:
                    continue
                if parent.table_name == "lemma":
                    result["lemma"] = ancestor["text"]
                else:
                    result["pos"] = ancestor["pos"]
                child = parent
                break
            else:
                break
        return result

    return await _atomic(db, operation)
