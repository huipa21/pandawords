from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import create, relate, visible
from app.domain.dictionary_keys import sense_key
from app.domain.identity import user_key
from app.services.dictionary import materialize_lemma
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_custom_sense_is_owned_attached_and_effective_only_for_creator(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    alice, bob = await make_user(), await make_user(role="admin")
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    result = await materialize_lemma(
        db,
        lexicon_reader,
        "run",
        selected_senses=[sense_key("en", "run", "verb", source_sense_id="run-move")],
    )
    shared_before = {
        table: await visible(db, table, None)
        for table in ("lemma", "lexeme", "sense", "has_lexeme", "has_sense")
    }
    response = await client.post(
        f"/api/dictionary/lexemes/{result.lexeme_ids[0]}/senses",
        headers=ah,
        json={"definition": "My own meaning", "gloss": {"zh": "自定义"}, "register": ["informal"]},
    )
    assert response.status_code == 201, response.text
    custom = response.json()
    assert custom["owner"] == alice.id and custom["table"] == "sense"
    assert custom["fields"]["source"] == "custom"
    assert custom["fields"]["register"] == ["informal"]
    custom_id = custom["id"]
    target = decode_rid(custom_id, "sense")
    edges = await visible(db, "has_sense", RecordID("user", user_key(alice.id)))
    edge = next(row for row in edges if row["out"] == target)
    assert edge["owner"] == RecordID("user", user_key(alice.id))
    assert edge["in"] == decode_rid(result.lexeme_ids[0], "lexeme")
    entry_path = f"/api/dictionary/lemmas/{result.lemma_id}/entry"
    own_entry = (await client.get(entry_path, headers=ah)).json()
    other_entry = (await client.get(entry_path, headers=bh)).json()
    assert custom in [sense for item in own_entry["lexemes"] for sense in item["senses"]]
    assert custom_id not in str(other_entry)
    path = f"/api/dictionary/sense/{custom_id}/override"
    assert (
        await client.put(path, headers=ah, json={"fields": {"definition": "Edited"}})
    ).status_code == 200
    for method in ("GET", "PUT", "PATCH", "DELETE"):
        kwargs: dict[str, Any] = (
            {"json": {"fields": {"definition": "Stolen"}}} if method in {"PUT", "PATCH"} else {}
        )
        assert (await client.request(method, path, headers=bh, **kwargs)).status_code == 404
    assert {table: await visible(db, table, None) for table in shared_before} == shared_before


async def test_private_lemma_entry_and_custom_lexeme_creation_isolation(
    client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user(role="admin")
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    user = RecordID("user", user_key(alice.id))
    lemma, lexeme = RecordID("lemma", uuid4().hex), RecordID("lexeme", uuid4().hex)
    await create(
        db,
        lemma,
        {
            "owner": user,
            "text": uuid4().hex,
            "lang": "en",
            "kind": "word",
            "freq_zipf": 0,
            "exam_tags": [],
            "source": "custom",
        },
    )
    await create(
        db,
        lexeme,
        {
            "owner": user,
            "pos": "noun",
            "etymology_no": 1,
            "forms": [],
            "pron": [],
        },
    )
    await relate(db, "has_lexeme", lemma, lexeme, {"owner": user})
    lemma_id, lexeme_id = encode_rid(lemma, "lemma"), encode_rid(lexeme, "lexeme")
    path = f"/api/dictionary/lemmas/{lemma_id}/entry"
    assert (await client.get(path, headers=ah)).status_code == 200
    assert (await client.get(path, headers=bh)).status_code == 404
    sense_path = f"/api/dictionary/lexemes/{lexeme_id}/senses"
    assert (
        await client.post(sense_path, headers=bh, json={"definition": "Stolen"})
    ).status_code == 404
    assert (
        await client.post(sense_path, headers=ah, json={"definition": "Owned"})
    ).status_code == 201
    for fields in (
        {"definition": ""},
        {"definition": " "},
        {"definition": "x", "owner": alice.id},
        {"definition": "x", "source": "shared"},
        {"definition": "x", "lexeme": lexeme_id},
    ):
        assert (await client.post(sense_path, headers=ah, json=fields)).status_code == 422
    for id in ("invalid", encode_rid(RecordID("lexeme", "missing"), "lexeme"), lemma_id):
        assert (
            await client.post(
                f"/api/dictionary/lexemes/{id}/senses", headers=ah, json={"definition": "x"}
            )
        ).status_code == 404
    for id in ("invalid", encode_rid(RecordID("lemma", "missing"), "lemma"), lexeme_id):
        assert (
            await client.get(f"/api/dictionary/lemmas/{id}/entry", headers=ah)
        ).status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/dictionary/lemmas/invalid/entry", None),
        ("POST", "/api/dictionary/lexemes/invalid/senses", {"definition": "x"}),
        ("GET", "/api/dictionary/sense/invalid/override", None),
        ("PUT", "/api/dictionary/sense/invalid/override", {"fields": {}}),
        ("PATCH", "/api/dictionary/sense/invalid/override", {"fields": {}}),
        ("DELETE", "/api/dictionary/sense/invalid/override", None),
        ("POST", "/api/notes", {"target_table": "sense", "target_id": "invalid", "text": "x"}),
        ("GET", "/api/notes?target_table=sense&target_id=invalid", None),
        ("GET", "/api/notes/invalid", None),
        ("PATCH", "/api/notes/invalid", {"text": "x"}),
        ("DELETE", "/api/notes/invalid", None),
    ],
)
async def test_all_dictionary_routes_require_authentication(
    client: AsyncClient, method: str, path: str, body: dict[str, Any] | None
) -> None:
    assert (await client.request(method, path, json=body)).status_code == 401
