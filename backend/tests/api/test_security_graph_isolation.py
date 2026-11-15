from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import encode_rid
from app.db import media_test_support as support
from app.db.dictionary_schema_test_support import create, relate
from app.domain.identity import user_key
from tests.api.auth_support import bearer, login
from tests.api.security_support import rid, same_not_found
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def test_graph_dictionary_and_edges_check_each_owner_independently(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
) -> None:
    alice, bob = await make_user(), await make_user(role="admin")
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    owner = RecordID("user", user_key(alice.id))
    lemma, lexeme = RecordID("lemma", uuid4().hex), RecordID("lexeme", uuid4().hex)
    await create(
        db,
        lemma,
        {
            "owner": owner,
            "text": uuid4().hex,
            "lang": "en",
            "kind": "word",
            "freq_zipf": 0,
            "exam_tags": [],
            "source": "custom",
        },
    )
    await create(
        db, lexeme, {"owner": owner, "pos": "noun", "etymology_no": 1, "forms": [], "pron": []}
    )
    await relate(db, "has_lexeme", lemma, lexeme, {"owner": owner})
    private_sense = encode_rid(await support.sense(db, alice.id), "sense")
    second_sense = encode_rid(await support.sense(db, alice.id), "sense")
    bob_sense = encode_rid(await support.sense(db, bob.id), "sense")
    relation = await client.post(
        "/api/relations",
        headers=ah,
        json={"start": private_sense, "end": second_sense, "type": "synonym"},
    )
    assert relation.status_code == 201
    relation_id = relation.json()["relation"]["id"]
    tag = (await client.post("/api/tags", headers=ah, json={"name": "Private"})).json()
    bob_tag = (await client.post("/api/tags", headers=bh, json={"name": "Own"})).json()
    private_target = {"target_table": "tag", "target_id": tag["id"]}
    absent_target = {"target_table": "tag", "target_id": rid("tag")}

    for method in ("PUT", "DELETE"):
        kwargs = {"json": private_target} if method == "PUT" else {"params": private_target}
        missing = {"json": absent_target} if method == "PUT" else {"params": absent_target}
        path = f"/api/tags/{bob_tag['id']}/members"
        hidden = await client.request(method, path, headers=bh, **kwargs)
        absent = await client.request(method, path, headers=bh, **missing)
        assert hidden.status_code == absent.status_code == 404
        assert hidden.json() == absent.json()
        await same_not_found(
            client,
            bh,
            method,
            f"/api/tags/{tag['id']}/members",
            f"/api/tags/{rid('tag')}/members",
            **(
                {"json": {"target_table": "sense", "target_id": bob_sense}}
                if method == "PUT"
                else {"params": {"target_table": "sense", "target_id": bob_sense}}
            ),
        )
    for path in ("/api/tags/assignments", "/api/notes"):
        hidden = await client.get(path, headers=bh, params=private_target)
        absent = await client.get(path, headers=bh, params=absent_target)
        assert hidden.status_code == absent.status_code == 404
        assert hidden.json() == absent.json()
    for path, hidden_body, absent_body in (
        ("/api/notes", {**private_target, "text": "Private"}, {**absent_target, "text": "Private"}),
        (
            "/api/notes/suggestions",
            {"target_table": "sense", "target_id": private_sense},
            {"target_table": "sense", "target_id": rid("sense")},
        ),
    ):
        hidden = await client.post(path, headers=bh, json=hidden_body)
        absent = await client.post(path, headers=bh, json=absent_body)
        assert hidden.status_code == absent.status_code == 404
        assert hidden.json() == absent.json()
    for template, table, record in (
        ("/api/dictionary/lemmas/{}/entry", "lemma", lemma),
        ("/api/dictionary/lemma/{}/phrases", "lemma", lemma),
        ("/api/dictionary/lexeme/{}/phrases", "lexeme", lexeme),
    ):
        await same_not_found(
            client,
            bh,
            "GET",
            template.format(encode_rid(record, table)),
            template.format(rid(table)),
        )
    await same_not_found(
        client,
        bh,
        "POST",
        f"/api/dictionary/lexemes/{encode_rid(lexeme, 'lexeme')}/senses",
        f"/api/dictionary/lexemes/{rid('lexeme')}/senses",
        json={"definition": "Changed"},
    )
    for path in ("/api/graph?focus_id={}", "/api/relations?sense_id={}"):
        await same_not_found(
            client, bh, "GET", path.format(private_sense), path.format(rid("sense"))
        )
    relation_errors = []
    for start in (private_sense, rid("sense")):
        response = await client.post(
            "/api/relations",
            headers=bh,
            json={"start": start, "end": bob_sense, "type": "synonym"},
        )
        assert response.status_code == 404
        relation_errors.append(response.json())
    assert relation_errors[0] == relation_errors[1]
    await same_not_found(
        client,
        bh,
        "DELETE",
        f"/api/relations/{relation_id}",
        f"/api/relations/{rid('relates_to')}",
    )
    assert (await client.get(f"/api/tags/{tag['id']}", headers=ah)).json() == tag
    assert (
        await client.get("/api/relations", headers=ah, params={"sense_id": private_sense})
    ).json()[0]["id"] == relation_id
