from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.api.dependencies import get_lexicon_reader
from app.core.config import Settings
from app.core.record_ids import encode_rid
from app.db import images as image_repository
from app.db import media_test_support as support
from app.domain.jobs import JobCreate
from app.services import jobs
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.api.security_support import rid, same_not_found
from tests.conftest import UserFactory
from tests.unit.test_image_validation import picture

pytestmark = pytest.mark.integration


async def test_private_records_and_nested_routes_hide_foreign_existence(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    test_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.dependency_overrides[get_lexicon_reader] = lambda: lexicon_reader
    monkeypatch.setattr(test_settings, "media_dir", tmp_path)
    monkeypatch.setattr(test_settings, "app_env", "development")
    alice, bob = await make_user(), await make_user(role="admin")
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    project = (await client.post("/api/projects", headers=ah, json={"name": "Private"})).json()
    tag = (await client.post("/api/tags", headers=ah, json={"name": "Private"})).json()
    shared_tag = encode_rid(await support.target(db), "tag")
    note = (
        await client.post(
            "/api/notes",
            headers=ah,
            json={"target_table": "tag", "target_id": shared_tag, "text": "Private"},
        )
    ).json()
    sentence = (
        await client.post("/api/content/sentence", headers=ah, json={"text": "cat."})
    ).json()
    passage = (await client.post("/api/content/passage", headers=ah, json={"text": "cat."})).json()
    private_sense = encode_rid(await support.sense(db, alice.id), "sense")
    shared_sense = encode_rid(await support.sense(db), "sense")
    image_path = f"/api/images/senses/{shared_sense}"
    upload = await client.post(
        image_path,
        headers={**ah, "Content-Type": "image/png", "request-id": "security-image-0001"},
        content=picture(),
    )
    assert upload.status_code == 200
    image = upload.json()
    job = await jobs.enqueue(
        db, JobCreate(type="noop", owner=alice.id, payload={"private": "synthetic"})
    )

    for method, tail, body in (
        ("GET", "", None),
        ("PATCH", "", {"name": "Changed"}),
        ("DELETE", "", None),
        ("GET", "/tree", None),
        ("PATCH", f"/tree/sense/{private_sense}/visibility", {"hidden": True}),
        ("GET", "/study-plan", None),
        ("PUT", "/study-plan/order", {"sense_ids": []}),
        ("POST", "/dictionary", {"lemma_key": ["en", "cat"], "selected_senses": []}),
    ):
        await same_not_found(
            client,
            bh,
            method,
            f"/api/projects/{project['id']}{tail}",
            f"/api/projects/{rid('project')}{tail}",
            json=body,
        )
    await same_not_found(
        client,
        bh,
        "GET",
        f"/api/graph/seeds?project_id={project['id']}",
        f"/api/graph/seeds?project_id={rid('project')}",
    )
    for kind, record in (("sentence", sentence), ("passage", passage)):
        for method, body in (("GET", None), ("PUT", {"text": "Changed"}), ("DELETE", None)):
            await same_not_found(
                client,
                bh,
                method,
                f"/api/content/{kind}/{record['id']}",
                f"/api/content/{kind}/{rid(kind)}",
                json=body,
            )
    await same_not_found(
        client,
        bh,
        "GET",
        f"/api/content/passage/{passage['id']}/reading",
        f"/api/content/passage/{rid('passage')}/reading",
    )
    for method, body in (
        ("PUT", {"sentence_id": sentence["id"]}),
        ("DELETE", None),
    ):
        await same_not_found(
            client,
            bh,
            method,
            f"/api/content/passage/{passage['id']}/sentences/0",
            f"/api/content/passage/{rid('passage')}/sentences/0",
            json=body,
        )
    for method, suffix, body in (
        ("GET", "", None),
        ("PUT", "", {"span": [0, 3], "sense_id": private_sense}),
        ("DELETE", f"/{rid('used_in')}", None),
    ):
        await same_not_found(
            client,
            bh,
            method,
            f"/api/content/sentence/{sentence['id']}/occurrences{suffix}",
            f"/api/content/sentence/{rid('sentence')}/occurrences{suffix}",
            json=body,
        )
    for resource, item, table, change in (
        ("/api/tags", tag, "tag", {"name": "Changed"}),
        ("/api/notes", note, "note", {"text": "Changed"}),
    ):
        for method, body in (("GET", None), ("PATCH", change), ("DELETE", None)):
            await same_not_found(
                client,
                bh,
                method,
                f"{resource}/{item['id']}",
                f"{resource}/{rid(table)}",
                json=body,
            )
    for method, body in (
        ("GET", None),
        ("PUT", {"fields": {"name": "Changed"}}),
        ("PATCH", {"fields": {"name": "Changed"}}),
        ("DELETE", None),
    ):
        await same_not_found(
            client,
            bh,
            method,
            f"/api/dictionary/tag/{tag['id']}/override",
            f"/api/dictionary/tag/{rid('tag')}/override",
            json=body,
        )
    for method, kwargs in (
        ("GET", {}),
        (
            "POST",
            {
                "headers": {"Content-Type": "image/png", "request-id": "security-image-0002"},
                "content": picture(),
            },
        ),
    ):
        extra_headers = kwargs.pop("headers", {})
        await same_not_found(
            client,
            {**bh, **extra_headers},
            method,
            f"/api/images/senses/{private_sense}",
            f"/api/images/senses/{rid('sense')}",
            **kwargs,
        )
    await same_not_found(
        client, bh, "DELETE", f"{image_path}/{image['id']}", f"{image_path}/{rid('media')}"
    )
    search_id = image_repository.key(alice.id, "private search")
    await image_repository.cache(db, alice.id, search_id, {"hits": [{"id": 17}]})
    selection = {"request_id": "security-select-001", "search_id": search_id, "result_id": 17}
    hidden = await client.post(f"{image_path}/pixabay", headers=bh, json=selection)
    absent = await client.post(
        f"{image_path}/pixabay", headers=bh, json={**selection, "search_id": "0" * 64}
    )
    assert hidden.status_code == absent.status_code == 422
    assert hidden.json() == absent.json()
    await same_not_found(
        client,
        bh,
        "POST",
        f"/api/images/senses/{private_sense}/pixabay",
        f"/api/images/senses/{rid('sense')}/pixabay",
        json=selection,
    )
    await same_not_found(
        client, bh, "GET", f"/api/media/{image['id']}", f"/api/media/{rid('media')}"
    )
    await same_not_found(client, bh, "GET", f"/api/jobs/{job.id}", f"/api/jobs/{uuid4().hex}")
    await same_not_found(
        client,
        bh,
        "GET",
        f"/api/notes/suggestions/{job.id}",
        f"/api/notes/suggestions/{uuid4().hex}",
    )

    assert (await client.get("/api/projects", headers=bh)).json()["items"] == []
    assert tag not in (await client.get("/api/tags", headers=bh)).json()
    assert (
        await client.get(
            "/api/notes", headers=bh, params={"target_table": "tag", "target_id": shared_tag}
        )
    ).json() == []
    assert (await client.get("/api/content/sentence", headers=bh)).json() == []
    assert (await client.get("/api/content/passage", headers=bh)).json() == []
    assert (await client.get(image_path, headers=bh)).json() == []
    assert project["id"] not in str((await client.get("/api/dashboard", headers=bh)).json())
    assert (await client.get(f"/api/projects/{project['id']}", headers=ah)).json() == project
    assert (await client.get(f"/api/tags/{tag['id']}", headers=ah)).json() == tag
    assert (await client.get(f"/api/notes/{note['id']}", headers=ah)).json() == note
    assert (
        await client.get(f"/api/content/sentence/{sentence['id']}", headers=ah)
    ).json() == sentence
    assert (await client.get(f"/api/content/passage/{passage['id']}", headers=ah)).json() == passage
    assert (await client.get(f"/api/media/{image['id']}", headers=ah)).content == picture()
