from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import create, relate
from app.db.project_schema_test_support import put_override
from app.domain.dictionary_keys import lexeme_key
from app.domain.identity import user_key
from app.services.dictionary import materialize_lemma
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).parents[1] / "fixtures" / "lexicon_small.sqlite"


@pytest.fixture(autouse=True)
def configured_app(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"lexicon_path": FIXTURE})


async def test_exact_components_order_pages_and_owner_filtering(
    client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user()
    headers = bearer(await login(client, alice.username))
    owner = RecordID("user", user_key(alice.id))
    other = RecordID("user", user_key(bob.id))
    reader = LexiconReader(FIXTURE)
    rain = await materialize_lemma(db, reader, "rain")
    phrase = await materialize_lemma(db, reader, "heavy rain")
    target = RecordID("lexeme", lexeme_key("en", "rain", "noun"))
    foreign_target = RecordID("lexeme", uuid4().hex)
    await create(
        db,
        foreign_target,
        {
            "pos": "noun",
            "etymology_no": 1,
            "forms": [],
            "pron": [],
            "owner": other,
        },
    )
    wrong_pos = RecordID("lexeme", lexeme_key("en", "rain", "verb"))
    substring = RecordID("lexeme", lexeme_key("en", "rainfall", "noun"))
    for component in (wrong_pos, substring):
        await create(
            db,
            component,
            {
                "pos": "noun" if component == substring else "verb",
                "etymology_no": 1,
                "forms": [],
                "pron": [],
            },
        )
    await relate(
        db, "has_lexeme", decode_rid(rain.lemma_id, "lemma"), foreign_target, {"owner": None}
    )
    private_phrase = ""
    for text, edge_owner, phrase_owner, component in [
        ("a rain", None, None, target),
        ("b rain", owner, owner, target),
        ("c rain", other, None, target),
        ("d rain", None, other, target),
        ("e rain", None, None, foreign_target),
        ("f rain", None, None, wrong_pos),
        ("g rain", None, None, substring),
    ]:
        rid = RecordID("lemma", uuid4().hex)
        await create(
            db,
            rid,
            {
                "text": text,
                "lang": "en",
                "kind": "phrase",
                "owner": phrase_owner,
                "freq_zipf": 0,
                "exam_tags": [],
                "source": "test",
            },
        )
        await relate(db, "contains", rid, component, {"owner": edge_owner, "position": 0})
        if phrase_owner == other:
            private_phrase = encode_rid(rid, "lemma")
    # A duplicate component edge must not duplicate a candidate.
    await relate(
        db,
        "contains",
        decode_rid(phrase.lemma_id, "lemma"),
        target,
        {"owner": owner, "position": 50},
    )
    url = f"/api/dictionary/lemma/{rain.lemma_id}/phrases"
    response = await client.get(url, headers=headers, params={"limit": 1})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["has_more"] and result["items"][0]["entry"]["lemma"]["fields"]["text"] == "a rain"
    second = (await client.get(url, headers=headers, params={"offset": 1, "limit": 1})).json()
    assert second["items"][0]["entry"]["lemma"]["fields"]["text"] == "b rain"
    last = (await client.get(url, headers=headers, params={"offset": 2, "limit": 1})).json()
    assert not last["has_more"]
    assert last["items"][0]["candidate"]["lemma"]["text"] == "heavy rain"
    assert last["items"][0]["candidate"]["lexemes"][0]["senses"]
    assert last["sources"]
    await put_override(db, owner, decode_rid(phrase.lemma_id, "lemma"), {"text": "My phrase label"})
    effective = (await client.get(url, headers=headers, params={"offset": 2, "limit": 1})).json()
    assert effective["items"][0]["entry"]["lemma"]["fields"]["text"] == "My phrase label"
    assert effective["items"][0]["candidate"]["lemma"]["text"] == "heavy rain"
    assert (await client.get(url, headers=headers)).json() == (
        await client.get(url, headers=headers)
    ).json()
    assert (await client.get(url, headers=headers, params={"offset": 10000})).json()["items"] == []
    lexeme_url = f"/api/dictionary/lexeme/{encode_rid(target, 'lexeme')}/phrases"
    assert (await client.get(lexeme_url, headers=headers)).json()["items"] == (
        await client.get(url, headers=headers)
    ).json()["items"]
    # A foreign has_lexeme edge cannot attach an unrelated word to rain.
    kick = await materialize_lemma(db, reader, "kick")
    await relate(db, "has_lexeme", decode_rid(kick.lemma_id, "lemma"), target, {"owner": other})
    empty = await client.get(f"/api/dictionary/lemma/{kick.lemma_id}/phrases", headers=headers)
    assert empty.json()["items"] == []
    for params in ({"limit": 0}, {"limit": 51}, {"offset": -1}, {"offset": 10001}):
        assert (await client.get(url, headers=headers, params=params)).status_code == 422
    assert (await client.get(url)).status_code == 401
    for table, rid in (
        ("lemma", "bad"),
        ("lemma", private_phrase),
        ("lemma", encode_rid(RecordID("lemma", uuid4().hex), "lemma")),
        ("lexeme", encode_rid(foreign_target, "lexeme")),
    ):
        assert (
            await client.get(f"/api/dictionary/{table}/{rid}/phrases", headers=headers)
        ).status_code == 404
    assert (
        await client.get(f"/api/dictionary/sense/{rain.lemma_id}/phrases", headers=headers)
    ).status_code == 422
