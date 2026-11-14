import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.errors import AppError
from app.db.auth import find_user
from app.db.migrate import run_migrations
from app.domain.admin import AdminUserUpdate
from app.services import admin
from tests.conftest import UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.fresh_db]


@pytest.mark.parametrize("change", [{"disabled": True}, {"role": "user"}])
async def test_sole_enabled_admin_with_disabled_admin(
    db: AsyncWsSurrealConnection, make_user: UserFactory, change: dict
) -> None:
    await run_migrations(db)
    enabled = await make_user(role="admin")
    disabled = await make_user(role="admin", disabled=True)
    payload = AdminUserUpdate.model_validate(change)
    with pytest.raises(AppError) as self_error:
        await admin.update_user(db, enabled.id, enabled.id, payload)
    assert self_error.value.code == "admin.self_protected"
    # A disabled admin holding a previously issued token cannot remove the last admin.
    with pytest.raises(AppError) as stale_error:
        await admin.update_user(db, disabled.id, enabled.id, payload)
    assert stale_error.value.code == "auth.forbidden"
    current = await find_user(db, enabled.id)
    assert current is not None and current.role == "admin" and not current.disabled
    demoted = await admin.update_user(db, enabled.id, disabled.id, AdminUserUpdate(role="user"))
    assert demoted.user.role == "user" and demoted.user.disabled
