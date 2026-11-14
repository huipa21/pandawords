"""Inspection and state changes for authentication integration tests."""

from datetime import UTC, datetime
from typing import Any

from surrealdb import AsyncSurrealConnection, RecordID

from app.db.auth import _rows
from app.domain.identity import user_key


def is_refresh_lookup(query: str) -> bool:
    return query.startswith("SELECT * FROM refresh_token WHERE token_hash")


def is_bootstrap_lookup(query: str) -> bool:
    return query.startswith("SELECT * FROM user WHERE role")


async def tokens_for(db: AsyncSurrealConnection, subject: str) -> list[dict[str, Any]]:
    return await _rows(
        db,
        "SELECT * FROM refresh_token WHERE user = $user;",
        {"user": RecordID("user", user_key(subject))},
    )


async def expire_token(db: AsyncSurrealConnection, subject: str, token_hash: str) -> None:
    await _rows(
        db,
        "UPDATE refresh_token SET expires_at = $expires WHERE user = $user AND token_hash = $hash;",
        {
            "user": RecordID("user", user_key(subject)),
            "hash": token_hash,
            "expires": datetime(2000, 1, 1, tzinfo=UTC),
        },
    )


async def disable_user(db: AsyncSurrealConnection, subject: str) -> None:
    await _rows(
        db,
        "UPDATE $user SET disabled = true WHERE id = $user;",
        {"user": RecordID("user", user_key(subject))},
    )


async def admins(db: AsyncSurrealConnection) -> list[dict[str, Any]]:
    return await _rows(db, "SELECT * FROM user WHERE role = $role;", {"role": "admin"})
