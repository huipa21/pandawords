"""Credential-free account administration, serialized against admin write skew."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.errors import ServerError
from surrealdb.types import Value

from app.core.errors import AppError
from app.db.auth import _atomic, _rows
from app.domain.admin import AdminUserPage, AdminUserUpdate
from app.domain.auth import UserCreate, UserRead
from app.domain.identity import user_key, user_subject


def _read(row: dict[str, Any]) -> UserRead:
    record = row["id"]
    if not isinstance(record, RecordID) or record.table_name != "user":
        raise ValueError("Invalid user record")
    return UserRead.model_validate({**row, "id": user_subject(str(record.id))})


async def _authorize(db: AsyncSurrealConnection, actor: str, txn: UUID) -> None:
    # A real shared write turns concurrent checks into conflicts retried by _atomic.
    guard = await _rows(
        db,
        "UPDATE admin_guard:singleton SET version += 1;",
        {},
        txn_id=txn,
    )
    if not guard:
        raise RuntimeError("Admin serialization guard is missing")
    users = await _rows(
        db,
        "SELECT id FROM $actor WHERE id = $actor AND role = 'admin' AND disabled = false "
        "AND must_change_password = false;",
        {"actor": RecordID("user", user_key(actor))},
        txn_id=txn,
    )
    if not users:
        raise AppError("auth.forbidden", 403, "Access denied.")


async def list_users(db: AsyncSurrealConnection, page: int, page_size: int) -> AdminUserPage:
    async def operation(txn: UUID) -> AdminUserPage:
        rows = await _rows(
            db,
            "SELECT id, username, role, disabled, must_change_password, source_lang, "
            "target_lang, prefs FROM user ORDER BY username, id "
            "LIMIT $limit START $start;",
            {"limit": page_size, "start": (page - 1) * page_size},
            txn_id=txn,
        )
        counts = await _rows(db, "SELECT count() AS total FROM user GROUP ALL;", {}, txn_id=txn)
        return AdminUserPage(
            items=[_read(row) for row in rows],
            total=counts[0]["total"] if counts else 0,
            page=page,
            page_size=page_size,
        )

    return await _atomic(db, operation)


async def create_user(
    db: AsyncSurrealConnection, actor: str, data: UserCreate, password_hash: str
) -> UserRead:
    async def operation(txn: UUID) -> UserRead:
        await _authorize(db, actor, txn)
        content: dict[str, Value] = {
            **data.model_dump(exclude={"password"}),
            "password_hash": password_hash,
        }
        rows = await _rows(
            db,
            "CREATE $user CONTENT $content RETURN id, username, role, disabled, "
            "must_change_password, source_lang, target_lang, prefs;",
            {"user": RecordID("user", uuid4().hex), "content": content},
            txn_id=txn,
        )
        return _read(rows[0])

    try:
        return await _atomic(db, operation)
    except ServerError as exc:
        if "user_username" in str(exc):
            raise AppError(
                "admin.username_taken", 409, "Username already exists.", "username"
            ) from None
        raise


async def update_user(
    db: AsyncSurrealConnection,
    actor: str,
    subject: str,
    data: AdminUserUpdate,
    password_hash: str | None,
) -> UserRead:
    async def operation(txn: UUID) -> UserRead:
        await _authorize(db, actor, txn)
        target = RecordID("user", user_key(subject))
        rows = await _rows(
            db,
            "SELECT id, username, role, disabled, must_change_password, source_lang, "
            "target_lang, prefs FROM $user WHERE id = $user;",
            {"user": target},
            txn_id=txn,
        )
        if not rows:
            raise AppError("admin.user_not_found", 404, "User not found.")
        current = _read(rows[0])
        disabled = current.disabled if data.disabled is None else data.disabled
        role = current.role if data.role is None else data.role
        removes_admin = role != "admin" or disabled
        if actor == subject and removes_admin:
            raise AppError("admin.self_protected", 409, "Cannot disable or demote yourself.")
        if current.role == "admin" and not current.disabled and removes_admin:
            admins = await _rows(
                db,
                "SELECT id FROM user WHERE role = 'admin' AND disabled = false;",
                {},
                txn_id=txn,
            )
            if len(admins) <= 1:
                raise AppError("admin.last_admin", 409, "Cannot remove the last enabled admin.")
        changes: dict[str, Value] = {"role": role, "disabled": disabled}
        if password_hash is not None:
            changes.update(password_hash=password_hash, must_change_password=True)
        updated = await _rows(
            db,
            "UPDATE $user MERGE $changes WHERE id = $user RETURN id, username, role, "
            "disabled, must_change_password, source_lang, target_lang, prefs;",
            {"user": target, "changes": changes},
            txn_id=txn,
        )
        if password_hash is not None or role != current.role or disabled != current.disabled:
            await _rows(
                db,
                "UPDATE refresh_token SET revoked_at = $now WHERE user = $user;",
                {"user": target, "now": datetime.now(UTC)},
                txn_id=txn,
            )
        return _read(updated[0])

    return await _atomic(db, operation)
