from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid, encode_rid
from app.db.auth_test_support import disable_user
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
URL = "/api/projects"


async def test_project_crud_and_plan_replacement(
    client: AsyncClient, make_user: UserFactory
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    created = await client.post(URL, headers=headers, json={"name": "  English  "})
    assert created.status_code == 201, created.text
    project = created.json()
    assert created.headers["cache-control"] == "no-store"
    assert set(project) == {
        "id",
        "name",
        "description",
        "target_lang",
        "source_lang",
        "plan",
        "created_at",
    }
    assert decode_rid(project["id"], "project").table_name == "project"
    assert project["name"] == "English"
    assert project["description"] == ""
    assert project["target_lang"] == "en" and project["source_lang"] == "zh"
    assert project["plan"] == {"daily_new": 20, "exam_date": None, "review_cap": None}
    assert project["created_at"].endswith("Z")
    url = f"{URL}/{project['id']}"
    read = await client.get(url, headers=headers)
    assert read.status_code == 200 and read.json() == project
    changes = {
        "name": "Exams",
        "description": "My preparation",
        "source_lang": "zh-CN",
        "target_lang": "en-GB",
        "plan": {"daily_new": 0, "review_cap": 100, "exam_date": "2027-01-15T08:00:00+08:00"},
    }
    updated = await client.patch(url, headers=headers, json=changes)
    assert updated.status_code == 200, updated.text
    result = updated.json()
    assert result == {
        **project,
        **changes,
        "plan": {"daily_new": 0, "review_cap": 100, "exam_date": "2027-01-15T00:00:00Z"},
    }
    assert (await client.get(url, headers=headers)).json() == result
    unchanged = await client.patch(url, headers=headers, json={})
    assert unchanged.status_code == 200 and unchanged.json() == result
    replacement = await client.patch(
        url, headers=headers, json={"plan": {"review_cap": None, "exam_date": None}}
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["plan"] == {"daily_new": 20, "review_cap": None, "exam_date": None}
    assert replacement.json()["description"] == changes["description"]
    cleared = await client.patch(url, headers=headers, json={"description": ""})
    assert cleared.status_code == 200 and cleared.json()["description"] == ""
    deleted = await client.delete(url, headers=headers)
    assert deleted.status_code == 204 and deleted.content == b""
    assert deleted.headers["cache-control"] == "no-store"
    for method in ("GET", "PATCH", "DELETE"):
        response = await client.request(method, url, headers=headers, json={})
        assert response.status_code == 404
        assert response.json()["code"] == "project.not_found"


async def test_project_pagination_and_cross_user_isolation(
    client: AsyncClient, make_user: UserFactory
) -> None:
    owner, other = await make_user(), await make_user(role="admin")
    headers = bearer(await login(client, owner.username))
    other_headers = bearer(await login(client, other.username))
    empty = await client.get(URL, headers=headers)
    assert empty.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}
    projects = []
    for name in ("First", "Second", "Third"):
        response = await client.post(URL, headers=headers, json={"name": name})
        assert response.status_code == 201, response.text
        projects.append(response.json())
    other_project = (
        await client.post(URL, headers=other_headers, json={"name": "Other user's project"})
    ).json()
    seen = []
    for page in range(1, 4):
        response = await client.get(URL, params={"page": page, "page_size": 1}, headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        result = response.json()
        assert (result["total"], result["page"], result["page_size"]) == (3, page, 1)
        seen.extend(result["items"])
    assert seen == list(reversed(projects))
    beyond = await client.get(URL, params={"page": 100, "page_size": 1}, headers=headers)
    assert beyond.json() == {"items": [], "total": 3, "page": 100, "page_size": 1}
    own = await client.get(URL, headers=other_headers)
    assert own.json()["items"] == [other_project] and own.json()["total"] == 1
    url = f"{URL}/{projects[0]['id']}"
    for method in ("GET", "PATCH", "DELETE"):
        response = await client.request(method, url, headers=other_headers, json={"name": "Stolen"})
        assert response.status_code == 404
        assert response.json() == {
            "code": "project.not_found",
            "message": "Project not found.",
            "field": None,
        }
        assert (await client.get(url, headers=headers)).json() == projects[0]
    spoofed = await client.post(URL, headers=headers, json={"name": "Spoofed", "owner": other.id})
    assert spoofed.status_code == 422


async def test_create_with_all_project_fields(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    data = {
        "name": "  Exams  ",
        "description": "Exam preparation",
        "source_lang": " zh-CN ",
        "target_lang": " en-GB ",
        "plan": {
            "daily_new": 15,
            "review_cap": 0,
            "exam_date": "2027-01-15T08:00:00+08:00",
        },
    }
    response = await client.post(URL, headers=headers, json=data)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result == {
        **data,
        "id": result["id"],
        "created_at": result["created_at"],
        "name": "Exams",
        "source_lang": "zh-CN",
        "target_lang": "en-GB",
        "plan": {**data["plan"], "exam_date": "2027-01-15T00:00:00Z"},
    }
    assert (await client.get(f"{URL}/{result['id']}", headers=headers)).json() == result


async def test_project_validation(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    created = await client.post(URL, headers=headers, json={"name": "Valid"})
    url = f"{URL}/{created.json()['id']}"
    invalid = [
        {"name": ""},
        {"name": " \t "},
        {"name": "x" * 129},
        {"name": None},
        {"description": None},
        {"description": "x" * 10001},
        {"target_lang": ""},
        {"source_lang": "   "},
        {"source_lang": None},
        {"target_lang": "x" * 36},
        {"target_lang": None},
        {"plan": None},
        {"plan": {"daily_new": -1}},
        {"plan": {"daily_new": 1.5}},
        {"plan": {"daily_new": True}},
        {"plan": {"daily_new": 9_223_372_036_854_775_808}},
        {"plan": {"daily_new": "10"}},
        {"plan": {"daily_new": None}},
        {"plan": {"review_cap": -1}},
        {"plan": {"review_cap": False}},
        {"plan": {"review_cap": 9_223_372_036_854_775_808}},
        {"plan": {"exam_date": "not-a-date"}},
        {"plan": {"exam_date": "2027-01-15T00:00:00"}},
        {"plan": {"unknown": 1}},
        {"owner": user.id},
        {"created_at": "2027-01-15T00:00:00Z"},
        {"id": "chosen"},
    ]
    for change in invalid:
        for method, target, payload in (
            ("POST", URL, {"name": "New", **change}),
            ("PATCH", url, change),
        ):
            response = await client.request(method, target, headers=headers, json=payload)
            assert response.status_code == 422, (method, change, response.text)
            assert response.json()["code"] == "validation.invalid"
    assert (await client.post(URL, headers=headers, json={})).status_code == 422
    assert (await client.get(url, headers=headers)).json() == created.json()
    assert (await client.get(URL, headers=headers)).json()["total"] == 1
    for query in (
        "page=0",
        "page=-1",
        "page=abc",
        "page_size=0",
        "page_size=101",
        "page=999999999999999999999999",
    ):
        response = await client.get(f"{URL}?{query}", headers=headers)
        assert response.status_code == 422


async def test_invalid_missing_and_wrong_table_project_ids(
    client: AsyncClient, make_user: UserFactory
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    missing = encode_rid(RecordID("project", uuid4().hex), "project")
    for id in (
        missing,
        "invalid",
        "project:unsafe",
        missing + "=",
        encode_rid(RecordID("lemma", ["en", "run"]), "lemma"),
    ):
        for method in ("GET", "PATCH", "DELETE"):
            response = await client.request(
                method, f"{URL}/{id}", headers=headers, json={"name": "Missing"}
            )
            assert response.status_code == 404, response.text
            assert response.json() == {
                "code": "project.not_found",
                "message": "Project not found.",
                "field": None,
            }


async def test_all_project_routes_require_enabled_authenticated_password_changed_user(
    client: AsyncClient, make_user: UserFactory, db: AsyncWsSurrealConnection
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    created = await client.post(URL, headers=headers, json={"name": "Private"})
    url = f"{URL}/{created.json()['id']}"
    forced = await make_user(must_change_password=True)
    forced_headers = bearer(await login(client, forced.username))
    await disable_user(db, user.id)
    for method, target in (
        ("GET", URL),
        ("POST", URL),
        ("GET", url),
        ("PATCH", url),
        ("DELETE", url),
    ):
        for auth, expected in (({}, 401), (headers, 401), (forced_headers, 403)):
            response = await client.request(method, target, headers=auth, json={"name": "Blocked"})
            assert response.status_code == expected
