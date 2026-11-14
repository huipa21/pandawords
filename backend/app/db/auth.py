"""Authentication lookups and atomic, user-scoped session mutations."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

import structlog
from anyio import CancelScope
from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.errors import QueryDetailKind, ServerError
from surrealdb.types import Value

from app.domain.auth import User, UserCreate
from app.domain.identity import user_key, user_subject


async def _rows(
    db: AsyncSurrealConnection,
    query: str,
    variables: dict[str, Value],
    *,
    txn_id: UUID | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(db, AsyncWsSurrealConnection):
        raise TypeError("Authentication requires the configured WebSocket connection")
    result = await db.query(query, variables, txn_id=txn_id).first()
    if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
        raise ValueError("Invalid authentication query result")
    return cast(list[dict[str, Any]], result)


def _user(row: dict[str, Any]) -> User:
    record = row["id"]
    if not isinstance(record, RecordID) or record.table_name != "user":
        raise ValueError("Invalid user record")
    return User.model_validate({**row, "id": user_subject(str(record.id))})


async def _rollback(db: AsyncSurrealConnection, txn: UUID) -> None:
    try:
        await db.cancel(txn)
    except Exception as exc:
        structlog.get_logger().warning(
            "auth_transaction_rollback_failed", error_type=type(exc).__name__
        )


async def _finish_cleanup[T](task: asyncio.Task[T]) -> tuple[T, asyncio.CancelledError | None]:
    cancellation: asyncio.CancelledError | None = None
    # AnyIO scopes and repeated native task cancellation must not strand a transaction.
    with CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                cancellation = exc
    return task.result(), cancellation


async def _begin(db: AsyncSurrealConnection) -> UUID:
    pending = asyncio.create_task(db.begin())
    try:
        txn = await asyncio.shield(pending)
    except asyncio.CancelledError:
        try:
            txn, _ = await _finish_cleanup(pending)
        except Exception as exc:
            structlog.get_logger().warning(
                "auth_transaction_begin_failed", error_type=type(exc).__name__
            )
        else:
            if txn is not None:
                await _finish_cleanup(asyncio.create_task(_rollback(db, txn)))
        raise
    if txn is None:
        raise RuntimeError("Database did not open an authentication transaction")
    return txn


async def _atomic[T](db: AsyncSurrealConnection, operation: Callable[[UUID], Awaitable[T]]) -> T:
    for attempt in range(5):
        txn = await _begin(db)
        try:
            result = await operation(txn)
            await db.commit(txn)
            return result
        except BaseException as exc:
            _, cancellation = await _finish_cleanup(asyncio.create_task(_rollback(db, txn)))
            if cancellation is not None:
                raise cancellation from None
            if (
                isinstance(exc, ServerError)
                and exc.details
                and exc.details.get("kind") == QueryDetailKind.TRANSACTION_CONFLICT
                and attempt < 4
            ):
                await asyncio.sleep(0.01 * (attempt + 1))
                continue
            raise
    raise RuntimeError("Unreachable transaction state")


async def find_user(db: AsyncSurrealConnection, subject: str) -> User | None:
    record = RecordID("user", user_key(subject))
    rows = await _rows(db, "SELECT * FROM $user WHERE id = $user;", {"user": record})
    return _user(rows[0]) if rows else None


async def find_by_username(db: AsyncSurrealConnection, username: str) -> User | None:
    # Credential lookup precedes authentication; no caller-supplied owner is trusted.
    rows = await _rows(
        db, "SELECT * FROM user WHERE username = $username LIMIT 1;", {"username": username}
    )
    return _user(rows[0]) if rows else None


async def create_user(db: AsyncSurrealConnection, data: UserCreate, password_hash: str) -> User:
    content: dict[str, Value] = {
        **data.model_dump(exclude={"password"}),
        "password_hash": password_hash,
    }
    rows = await _rows(
        db,
        "CREATE $user CONTENT $content;",
        {"user": RecordID("user", uuid4().hex), "content": content},
    )
    return _user(rows[0])


async def bootstrap_admin(db: AsyncSurrealConnection, data: UserCreate, password_hash: str) -> User:
    async def operation(txn: UUID) -> User:
        rows = await _rows(
            db, "SELECT * FROM user WHERE role = $role LIMIT 1;", {"role": "admin"}, txn_id=txn
        )
        if rows:
            return _user(rows[0])
        content: dict[str, Value] = {
            **data.model_dump(exclude={"password"}),
            "password_hash": password_hash,
        }
        rows = await _rows(
            db,
            "CREATE $user CONTENT $content;",
            {"user": RecordID("user", "bootstrap_admin"), "content": content},
            txn_id=txn,
        )
        return _user(rows[0])

    return await _atomic(db, operation)


async def has_admin(db: AsyncSurrealConnection) -> bool:
    return bool(
        await _rows(db, "SELECT id FROM user WHERE role = $role LIMIT 1;", {"role": "admin"})
    )


async def issue_refresh(
    db: AsyncSurrealConnection,
    subject: str,
    token_hash: str,
    expires_at: datetime,
    expected_password_hash: str | None = None,
) -> User | None:
    async def operation(txn: UUID) -> User | None:
        owner = RecordID("user", user_key(subject))
        rows = await _rows(
            db,
            "SELECT * FROM $user WHERE id = $user AND disabled = false;",
            {"user": owner},
            txn_id=txn,
        )
        if not rows:
            return None
        if (
            expected_password_hash is not None
            and rows[0]["password_hash"] != expected_password_hash
        ):
            return None
        await _rows(
            db,
            "CREATE $refresh_id SET user = $user, token_hash = $hash, expires_at = $expires;",
            {
                "refresh_id": RecordID("refresh_token", uuid4().hex),
                "user": owner,
                "hash": token_hash,
                "expires": expires_at,
            },
            txn_id=txn,
        )
        return _user(rows[0])

    return await _atomic(db, operation)


def _chain(rows: list[dict[str, Any]], start: RecordID) -> list[Value]:
    # Existing replacement links define a family, including ancestors of the presented token.
    family = {str(start)}
    changed = True
    while changed:
        changed = False
        for row in rows:
            left, right = str(row["id"]), str(row.get("replaced_by"))
            if row.get("replaced_by") is not None and (left in family or right in family):
                previous = len(family)
                family.update((left, right))
                changed |= len(family) != previous
    return [row["id"] for row in rows if str(row["id"]) in family]


async def consume_refresh(
    db: AsyncSurrealConnection,
    token_hash: str,
    now: datetime,
    replacement_hash: str | None = None,
    expires_at: datetime | None = None,
    subject: str | None = None,
    reject_forced: bool = False,
) -> User | None:
    async def operation(txn: UUID) -> User | None:
        # A hash is itself the bearer credential. All subsequent operations bind its user.
        matches = await _rows(
            db,
            "SELECT * FROM refresh_token WHERE token_hash = $hash LIMIT 1;",
            {"hash": token_hash},
            txn_id=txn,
        )
        if not matches:
            return None
        token = matches[0]
        owner = token["user"]
        if subject is not None and owner != RecordID("user", user_key(subject)):
            return None
        rows = await _rows(
            db, "SELECT * FROM refresh_token WHERE user = $user;", {"user": owner}, txn_id=txn
        )
        users = await _rows(
            db,
            "SELECT * FROM $user WHERE id = $user AND disabled = false;",
            {"user": owner},
            txn_id=txn,
        )
        if (
            replacement_hash is None
            or token.get("revoked_at") is not None
            or token["expires_at"] <= now
            or not users
        ):
            await _rows(
                db,
                "UPDATE refresh_token SET revoked_at = $now WHERE user = $user AND id IN $family;",
                {"now": now, "user": owner, "family": _chain(rows, token["id"])},
                txn_id=txn,
            )
            return None
        if reject_forced and users[0]["must_change_password"]:
            return _user(users[0])
        replacement = RecordID("refresh_token", uuid4().hex)
        await _rows(
            db,
            "CREATE $replacement SET user = $user, token_hash = $hash, expires_at = $expires;"
            "UPDATE refresh_token SET revoked_at = $now, replaced_by = $replacement "
            "WHERE user = $user AND id = $refresh_id;",
            {
                "replacement": replacement,
                "user": owner,
                "hash": replacement_hash,
                "expires": expires_at,
                "now": now,
                "refresh_id": token["id"],
            },
            txn_id=txn,
        )
        return _user(users[0])

    return await _atomic(db, operation)
