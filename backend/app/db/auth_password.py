from datetime import datetime
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID

from app.db.auth import _atomic, _rows, _user
from app.domain.auth import User
from app.domain.identity import user_key


async def change_password(
    db: AsyncSurrealConnection,
    subject: str,
    expected_hash: str,
    password_hash: str,
    token_hash: str,
    now: datetime,
    expires_at: datetime,
) -> User | None:
    async def operation(txn: UUID) -> User | None:
        owner = RecordID("user", user_key(subject))
        users = await _rows(
            db,
            "UPDATE $user SET password_hash = $password_hash, must_change_password = false "
            "WHERE id = $user AND disabled = false AND password_hash = $expected_hash;",
            {"user": owner, "password_hash": password_hash, "expected_hash": expected_hash},
            txn_id=txn,
        )
        if not users:
            return None
        await _rows(
            db,
            "UPDATE refresh_token SET revoked_at = $now WHERE user = $user;"
            "CREATE $refresh_id SET user = $user, token_hash = $hash, expires_at = $expires;",
            {
                "user": owner,
                "now": now,
                "refresh_id": RecordID("refresh_token", uuid4().hex),
                "hash": token_hash,
                "expires": expires_at,
            },
            txn_id=txn,
        )
        return _user(users[0])

    return await _atomic(db, operation)
