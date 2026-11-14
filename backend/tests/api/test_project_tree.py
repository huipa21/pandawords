from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.config import Settings
from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import create, relate, visible
from app.db.project_schema_test_support import owned, put_override
from app.domain.dictionary_keys import lexeme_key, sense_key
from app.domain.identity import user_key
from app.services.dictionary import materialize_lemma
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 14, tzinfo=UTC)


@pytest.fixture
def test_settings(job_settings: Settings) -> Settings:
    return job_settings


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def include(
    db: AsyncWsSurrealConnection,
    owner: RecordID,
    project: RecordID,
    target: RecordID,
    hidden: bool = False,
) -> dict[str, Any]:
    return await relate(
        db, "includes", project, target, {"owner": owner, "hidden": hidden, "added_at": NOW}
    )


async def test_selection_overlays_and_independent_hide_restore(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    alice, bob = await make_user(), await make_user()
    user, other = RecordID("user", user_key(alice.id)), RecordID("user", user_key(bob.id))
    headers = bearer(await login(client, alice.username))
    project = (await client.post("/api/projects", headers=headers, json={"name": "Words"})).json()
    project_id = decode_rid(project["id"], "project")
    url = f"/api/projects/{project['id']}/tree"
    assert (await client.get(url, headers=headers)).json()["items"] == []
    entry = await materialize_lemma(db, lexicon_reader, "run")  # Broad shared cache.
    await materialize_lemma(
        db,
        lexicon_reader,
        "run",
        selected_senses=[sense_key("en", "run", "verb", source_sense_id="run-flow")],
    )
    lemma = decode_rid(entry.lemma_id, "lemma")
    lexeme = RecordID("lexeme", lexeme_key("en", "run", "verb"))
    lexeme_id = encode_rid(lexeme, "lexeme")
    move = RecordID("sense", sense_key("en", "run", "verb", source_sense_id="run-move"))
    operate = RecordID("sense", sense_key("en", "run", "verb", source_sense_id="run-operate"))
    await include(db, user, project_id, lemma)
    empty = (await client.get(url, headers=headers)).json()
    assert empty["total"] == 1 and empty["items"][0]["lexemes"] == []
    await include(db, user, project_id, move)
    await include(db, user, project_id, operate)
    before = {table: await visible(db, table, None) for table in ("lemma", "lexeme", "sense")}
    await put_override(db, user, lemma, {"text": "My run"})
    await put_override(db, user, lexeme, {"pos": "my verb"})
    await put_override(db, user, move, {"definition": "My meaning", "gloss": {"fr": "courir"}})
    await put_override(db, other, move, {"definition": "Other user's edit"})
    response = await client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    node = response.json()["items"][0]
    assert node["lemma"]["fields"]["text"] == "My run"
    group = node["lexemes"][0]
    assert group["lexeme"]["fields"]["pos"] == "my verb" and not group["hidden"]
    assert {s["sense"]["id"] for s in group["senses"]} == {
        encode_rid(move, "sense"),
        encode_rid(operate, "sense"),
    }
    effective = next(
        s["sense"] for s in group["senses"] if s["sense"]["id"] == encode_rid(move, "sense")
    )
    assert effective["fields"]["definition"] == "My meaning"
    assert effective["fields"]["gloss"] == {"zh": "跑", "fr": "courir"}
    baseline = await owned(db, "includes", user)

    async def toggle(table: str, rid: str, hidden: bool) -> dict[str, Any]:
        result = await client.patch(
            f"{url}/{table}/{rid}/visibility", headers=headers, json={"hidden": hidden}
        )
        assert result.status_code == 200, result.text
        return result.json()

    sense_id = encode_rid(move, "sense")
    hidden_sense = await toggle("sense", sense_id, True)
    marker = await toggle("lexeme", lexeme_id, True)
    assert (await client.get(url, headers=headers)).json()["items"][0]["lexemes"] == []
    management = (await client.get(url, headers=headers, params={"include_hidden": True})).json()
    assert management["items"][0]["lexemes"][0]["hidden"]
    assert all(s["effective_hidden"] for s in management["items"][0]["lexemes"][0]["senses"])
    assert await toggle("lexeme", lexeme_id, False) == {**marker, "hidden": False}
    restored = (await client.get(url, headers=headers)).json()["items"][0]["lexemes"][0]
    assert [s["sense"]["id"] for s in restored["senses"]] == [encode_rid(operate, "sense")]
    await toggle("lemma", entry.lemma_id, True)
    assert (await client.get(url, headers=headers)).json()["total"] == 0
    management = (await client.get(url, headers=headers, params={"include_hidden": True})).json()
    assert management["total"] == 1 and management["items"][0]["hidden"]
    assert all(s["effective_hidden"] for s in management["items"][0]["lexemes"][0]["senses"])
    await toggle("lemma", entry.lemma_id, False)
    assert await toggle("sense", sense_id, False) == {**hidden_sense, "hidden": False}
    after = await owned(db, "includes", user)
    for row in baseline:
        assert next(item for item in after if item["id"] == row["id"]) == row
    assert {table: await visible(db, table, None) for table in before} == before
    assert len(after) == len(baseline) + 1


async def test_project_rows_edges_and_memberships_cannot_cross_users(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    alice, bob = await make_user(), await make_user()
    user, other = RecordID("user", user_key(alice.id)), RecordID("user", user_key(bob.id))
    headers, foreign_headers = (
        bearer(await login(client, alice.username)),
        bearer(await login(client, bob.username)),
    )
    project = (await client.post("/api/projects", headers=headers, json={"name": "Own"})).json()
    second = (await client.post("/api/projects", headers=headers, json={"name": "Second"})).json()
    foreign = (
        await client.post("/api/projects", headers=foreign_headers, json={"name": "Foreign"})
    ).json()
    project_id = decode_rid(project["id"], "project")
    entry = await materialize_lemma(db, lexicon_reader, "bank")
    lemma, lexeme = decode_rid(entry.lemma_id, "lemma"), decode_rid(entry.lexeme_ids[0], "lexeme")
    shared = decode_rid(entry.selected_sense_ids[0], "sense")
    await include(db, user, project_id, lemma)
    await include(db, user, project_id, shared)
    private = RecordID("sense", uuid4().hex)
    fields = next(row for row in await visible(db, "sense", None) if row["id"] == shared)
    fields = {key: value for key, value in fields.items() if key != "id"}
    await create(db, private, cast(dict[str, Value], {**fields, "owner": other}))
    await relate(db, "has_sense", lexeme, private, {"owner": user, "rank": 9})
    await include(db, user, project_id, private)  # Corrupt endpoint ownership.
    owned_sense = RecordID("sense", uuid4().hex)
    await create(db, owned_sense, cast(dict[str, Value], {**fields, "owner": user}))
    await relate(db, "has_sense", lexeme, owned_sense, {"owner": other, "rank": 8})
    await include(db, user, project_id, owned_sense)  # Foreign relation to own content.
    foreign_membership_sense = decode_rid(entry.selected_sense_ids[-1], "sense")
    await include(db, other, project_id, foreign_membership_sense)
    private_lexeme = RecordID("lexeme", uuid4().hex)
    await create(
        db,
        private_lexeme,
        {"owner": other, "pos": "noun", "etymology_no": 1, "forms": [], "pron": []},
    )
    await relate(db, "has_lexeme", lemma, private_lexeme, {"owner": user})
    await relate(db, "has_sense", private_lexeme, shared, {"owner": user, "rank": 0})
    edge_only_lexeme = RecordID("lexeme", uuid4().hex)
    await create(
        db,
        edge_only_lexeme,
        {"owner": user, "pos": "noun", "etymology_no": 1, "forms": [], "pron": []},
    )
    await relate(db, "has_lexeme", lemma, edge_only_lexeme, {"owner": other})
    await relate(db, "has_sense", edge_only_lexeme, shared, {"owner": user, "rank": 0})
    private_lemma = RecordID("lemma", uuid4().hex)
    await create(
        db,
        private_lemma,
        {
            "owner": other,
            "text": uuid4().hex,
            "lang": "en",
            "kind": "word",
            "freq_zipf": 0,
            "exam_tags": [],
            "source": "custom",
        },
    )
    await include(db, user, project_id, private_lemma)
    url = f"/api/projects/{project['id']}/tree"
    response = await client.get(url, headers=headers, params={"include_hidden": True})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert [
        s["sense"]["id"]
        for group in response.json()["items"][0]["lexemes"]
        for s in group["senses"]
    ] == [encode_rid(shared, "sense")]
    assert (await client.get(f"/api/projects/{second['id']}/tree", headers=headers)).json()[
        "items"
    ] == []
    for project_rid, actor in (
        (project["id"], foreign_headers),
        (foreign["id"], headers),
        ("bad", headers),
    ):
        path = f"/api/projects/{project_rid}/tree"
        assert (await client.get(path, headers=actor)).status_code == 404
        assert (
            await client.patch(
                f"{path}/lemma/{entry.lemma_id}/visibility", headers=actor, json={"hidden": True}
            )
        ).status_code == 404
    before = await owned(db, "includes", user)
    for table, target in (
        ("sense", private),
        ("lexeme", private_lexeme),
        ("lexeme", edge_only_lexeme),
        ("lemma", private_lemma),
        ("sense", foreign_membership_sense),
    ):
        result = await client.patch(
            f"{url}/{table}/{encode_rid(target, table)}/visibility",
            headers=headers,
            json={"hidden": True},
        )
        assert result.status_code == 404, result.text
    assert await owned(db, "includes", user) == before


async def test_pagination_bounds_validation_and_auth(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user()
    owner = RecordID("user", user_key(user.id))
    headers = bearer(await login(client, user.username))
    project = (await client.post("/api/projects", headers=headers, json={"name": "Paged"})).json()
    project_id = decode_rid(project["id"], "project")
    for text in ("run", "bank", "decision"):
        entry = await materialize_lemma(db, lexicon_reader, text)
        await include(db, owner, project_id, decode_rid(entry.lemma_id, "lemma"))
        for rid in entry.selected_sense_ids:
            await include(db, owner, project_id, decode_rid(rid, "sense"))
    url = f"/api/projects/{project['id']}/tree"
    full = (await client.get(url, headers=headers)).json()
    pages = [
        (await client.get(url, headers=headers, params={"page": page, "page_size": 1})).json()
        for page in (1, 2, 3, 4)
    ]
    assert [page["items"][0] for page in pages[:3]] == full["items"]
    assert all(page["total"] == 3 for page in pages)
    assert pages[-1]["items"] == []
    for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}, {"page": 2147483648}):
        assert (await client.get(url, headers=headers, params=params)).status_code == 422
    assert (await client.get(url)).status_code == 401
    patch_url = f"{url}/lemma/{entry.lemma_id}/visibility"
    assert (await client.patch(patch_url, json={"hidden": True})).status_code == 401
    for body in ({"hidden": "false"}, {"hidden": None}, {"hidden": True, "owner": user.id}, {}):
        assert (await client.patch(patch_url, headers=headers, json=body)).status_code == 422
    assert (
        await client.patch(f"{url}/sense/bad/visibility", headers=headers, json={"hidden": True})
    ).status_code == 404
    monkeypatch.setattr("app.db.project_tree.MAX_PAGE_NODES", 1)
    assert (await client.get(url, headers=headers)).status_code == 413
    monkeypatch.setattr("app.db.project_tree.MAX_PAGE_NODES", 2000)
    monkeypatch.setattr("app.db.project_tree.MAX_MEMBERSHIPS", 1)
    assert (await client.get(url, headers=headers)).status_code == 413
