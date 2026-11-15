from surrealdb import AsyncSurrealConnection, RecordID

from app.db.auth import _rows, _user
from app.domain.auth import User
from app.domain.identity import user_key
from app.domain.profile import ProfileUpdate


async def update_profile(
    db: AsyncSurrealConnection, subject: str, data: ProfileUpdate
) -> User | None:
    rows = await _rows(
        db,
        "UPDATE $user SET full_name = $full_name, email = $email, avatar = $avatar "
        "WHERE id = $user AND disabled = false AND must_change_password = false RETURN AFTER;",
        {
            "user": RecordID("user", user_key(subject)),
            "full_name": data.full_name,
            "email": data.email,
            "avatar": data.avatar,
        },
    )
    return _user(rows[0]) if rows else None
