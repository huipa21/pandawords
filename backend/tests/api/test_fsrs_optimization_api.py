import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.memory_schema_test_support import owned
from app.db.srs import user_record
from app.worker.runtime import run_once
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
URL = "/api/srs/optimization"


@pytest.fixture
def test_settings(job_settings: Settings) -> Settings:
    return job_settings


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def test_authenticated_owner_only_status_and_bounded_deduplicated_requests(
    db: AsyncWsSurrealConnection, client: AsyncClient, make_user: UserFactory
) -> None:
    user, other = await make_user(), await make_user()
    headers = bearer(await login(client, user.username))
    foreign_headers = bearer(await login(client, other.username))
    assert (await client.get(URL)).status_code == 401
    assert (await client.post(URL)).status_code == 401
    for _ in range(2):
        response = await client.post(f"{URL}?owner={other.id}", headers=headers)
        assert response.status_code == 202
        assert response.headers["cache-control"] == "no-store"
    jobs = await owned(db, "job", user_record(user.id))
    assert len(jobs) == 1 and jobs[0]["type"] == "srs_optimize"
    assert await owned(db, "job", user_record(other.id)) == []
    assert await run_once(db)
    result = await client.get(URL, headers=headers)
    assert result.json()["status"] == "insufficient_history"
    assert result.headers["cache-control"] == "no-store"
    assert (await owned(db, "job", user_record(user.id)))[0]["status"] == "done"
    assert (await client.post(URL, headers=headers)).json() == result.json()
    assert len(await owned(db, "job", user_record(user.id))) == 1
    assert (await client.get(f"{URL}?owner={user.id}", headers=foreign_headers)).json()[
        "status"
    ] == "not_run"
