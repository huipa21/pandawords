from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.domain.jobs import JobCreate
from app.services import jobs
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_job_status_owner_isolation_and_safe_ids(
    client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    owner, other = await make_user(), await make_user()
    owner_headers = bearer(await login(client, owner.username))
    other_headers = bearer(await login(client, other.username))
    job = await jobs.enqueue(
        db, JobCreate(type="noop", owner=owner.id, payload={"token": "private-credential"})
    )
    shared = await jobs.enqueue(db, JobCreate(type="noop"))
    response = await client.get(f"/api/jobs/{job.id}", headers=owner_headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "id": job.id,
        "type": "noop",
        "status": "queued",
        "attempts": 0,
        "run_after": job.run_after.isoformat().replace("+00:00", "Z"),
        "error": None,
    }
    assert "private-credential" not in response.text
    assert "payload" not in response.text
    assert "owner" not in response.text
    hidden = await client.get(f"/api/jobs/{job.id}", headers=other_headers)
    assert hidden.status_code == 404
    for key in (shared.id, uuid4().hex, "job:malformed", "invalid", "⟨unsafe⟩"):
        absent = await client.get(f"/api/jobs/{key}", headers=owner_headers)
        assert absent.status_code == 404
        assert absent.json() == hidden.json()
    assert (await client.get(f"/api/jobs/{job.id}")).status_code == 401


async def test_jobs_require_password_change_and_enabled_account(
    client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    from app.db.auth_test_support import disable_user

    forced = await make_user(must_change_password=True)
    job = await jobs.enqueue(db, JobCreate(type="noop", owner=forced.id))
    headers = bearer(await login(client, forced.username))
    assert (await client.get(f"/api/jobs/{job.id}", headers=headers)).status_code == 403
    owner = await make_user()
    headers = bearer(await login(client, owner.username))
    await disable_user(db, owner.id)
    assert (await client.get(f"/api/jobs/{job.id}", headers=headers)).status_code == 401
