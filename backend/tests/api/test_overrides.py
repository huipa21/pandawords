from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import create, visible
from app.domain.dictionary import DictionaryTable
from app.domain.dictionary_keys import sense_key
from app.services.dictionary import materialize_lemma, read_record
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_override_merge_replace_reset_and_shared_immutability(
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
    sense = result.selected_sense_ids[0]
    target = decode_rid(sense, "sense")
    shared = await visible(db, "sense", None)
    original = next(row for row in shared if row["id"] == target)
    path = f"/api/dictionary/sense/{sense}/override"
    entry_path = f"/api/dictionary/lemmas/{result.lemma_id}/entry"

    async def effective(headers: dict[str, str]) -> dict[str, Any]:
        response = await client.get(entry_path, headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        return next(
            item["fields"]
            for lexeme in response.json()["lexemes"]
            for item in lexeme["senses"]
            if item["id"] == sense
        )

    assert (await client.get(path, headers=ah)).status_code == 404
    response = await client.put(
        path, headers=ah, json={"fields": {"definition": "Alice", "gloss": {"fr": "courir"}}}
    )
    assert response.status_code == 200, response.text
    assert response.json()["fields"] == {"definition": "Alice", "gloss": {"fr": "courir"}}
    assert response.json()["target_id"] == sense
    assert (await client.get(path, headers=bh)).status_code == 404
    assert (await effective(ah))["definition"] == "Alice"
    assert (await effective(bh))["definition"] == original["definition"]
    assert (await effective(ah))["gloss"] == {**original["gloss"], "fr": "courir"}
    assert (await client.get(path, headers=ah)).json() == response.json()
    assert (
        await client.put(path, headers=bh, json={"fields": {"definition": "Bob"}})
    ).status_code == 200
    patched = await client.patch(
        path, headers=ah, json={"fields": {"gloss": {"zh": "自己的释义"}, "register": ["informal"]}}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["fields"]["gloss"] == {"fr": "courir", "zh": "自己的释义"}
    assert patched.json()["fields"]["register"] == ["informal"]
    assert patched.json()["fields"]["definition"] == "Alice"
    assert (await effective(ah))["register"] == ["informal"]
    replaced = await client.put(path, headers=ah, json={"fields": {"examples": []}})
    assert replaced.status_code == 200
    assert replaced.json()["fields"] == {"examples": []}
    assert (await effective(ah))["definition"] == original["definition"]
    assert (await client.put(path, headers=ah, json={"fields": {}})).json()["fields"] == {}
    assert (await client.delete(path, headers=ah)).status_code == 204
    assert (await client.delete(path, headers=ah)).status_code == 204
    assert (await client.get(path, headers=ah)).status_code == 404
    assert await effective(ah) == {
        key: value for key, value in original.items() if key not in {"id", "owner"}
    }
    assert (await effective(bh))["definition"] == "Bob"
    assert next(row for row in await visible(db, "sense", None) if row["id"] == target) == original


@pytest.mark.parametrize(
    "fields",
    [
        {"owner": "user:foreign"},
        {"id": "sense:changed"},
        {"in": "lexeme:changed"},
        {"out": "sense:changed"},
        {"source": "changed"},
        {"definition": None},
        {"definition": 1},
        {"rank": True},
        {"rank": -1},
        {"rank": 2**63},
        {"common": "true"},
        {"examples": ["ok", 1]},
        {"gloss": {"zh": {"owner": "bad"}}},
        {"gloss": {"not a language": "bad"}},
        {"pron": [{"accent": "US", "ipa": "a", "audio": "media:foreign"}]},
        {"text": "not a sense field"},
    ],
)
async def test_override_rejects_identity_pointers_and_invalid_fields(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    fields: dict[str, Any],
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    result = await materialize_lemma(
        db,
        lexicon_reader,
        "run",
        selected_senses=[sense_key("en", "run", "verb", source_sense_id="run-move")],
    )
    path = f"/api/dictionary/sense/{result.selected_sense_ids[0]}/override"
    for method in ("PUT", "PATCH"):
        response = await client.request(method, path, headers=headers, json={"fields": fields})
        assert response.status_code == 422, response.text
    assert (await client.get(path, headers=headers)).status_code == 404


@pytest.mark.parametrize(
    ("table", "base", "fields"),
    [
        (
            "lemma",
            {
                "text": "unique",
                "lang": "en",
                "kind": "word",
                "freq_zipf": 0,
                "exam_tags": [],
                "source": "fixture",
            },
            {"text": "My display", "cefr": "B1"},
        ),
        (
            "lexeme",
            {"pos": "verb", "etymology_no": 1, "forms": [], "pron": []},
            {
                "forms": [{"form": "ran", "tags": ["past"]}, {"form": "run", "tags": []}],
                "pron": [{"accent": "US", "ipa": "ræn"}],
            },
        ),
        (
            "sense",
            {
                "definition": "base",
                "gloss": {"zh": "原文"},
                "register": [],
                "domain": [],
                "examples": [],
                "rank": 0,
                "common": False,
                "source": "fixture",
            },
            {"rank": 2, "common": True, "domain": ["custom"]},
        ),
        ("morpheme", {"text": "pre-", "type": "prefix"}, {"meaning": "My meaning"}),
        ("tag", {"kind": "custom", "name": "base"}, {"name": "My tag"}),
        (
            "sentence",
            {"text": "Base.", "lang": "en", "translation": {}, "source": "fixture"},
            {"text": "Edited.", "translation": {"zh": "翻译"}},
        ),
        (
            "passage",
            {"title": "Base", "text": "Base.", "lang": "en", "source": "fixture"},
            {"title": "Mine", "text": "Edited."},
        ),
    ],
)
async def test_typed_overlays_on_each_permitted_dictionary_table(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    table: DictionaryTable,
    base: dict[str, Value],
    fields: dict[str, Any],
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    target = RecordID(table, uuid4().hex)
    if table == "lemma":
        base = {**base, "text": uuid4().hex}
    original = await create(db, target, base)
    id = encode_rid(target, table)
    path = f"/api/dictionary/{table}/{id}/override"
    payload = fields
    if table == "lexeme":
        payload = {**fields, "forms": [{"form": "ran", "tags": ["past"]}, {"form": "run"}]}
    response = await client.put(path, headers=headers, json={"fields": payload})
    assert response.status_code == 200, response.text
    assert response.json()["fields"] == fields
    effective = await read_record(db, user.id, id, table)
    assert effective is not None
    assert all(effective.fields[key] == value for key, value in fields.items())
    assert next(row for row in await visible(db, table, None) if row["id"] == target) == original
    assert (await client.delete(path, headers=headers)).status_code == 204
    restored = await read_record(db, user.id, id, table)
    assert restored is not None
    assert restored.fields == {
        key: value for key, value in original.items() if key not in {"id", "owner"}
    }
