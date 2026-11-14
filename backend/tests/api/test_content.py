import asyncio
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from surrealdb import AsyncSurrealConnection

from app.api.dependencies import get_lexicon_reader
from app.core.errors import LlmUnavailable
from app.core.record_ids import decode_rid, encode_rid
from app.db import content_test_support as support
from app.domain.content import ContentCreate
from app.services import content
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
BASE = "/api/content"


@pytest.fixture(autouse=True)
def offline_reader(app: FastAPI, lexicon_reader: LexiconReader) -> None:
    app.dependency_overrides[get_lexicon_reader] = lambda: lexicon_reader


async def test_ingestion_retries_reuse_unicode_manual_resolution_and_delete(
    client: AsyncClient,
    make_user: UserFactory,
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    data = {"text": "🙂 cats bank cats xyzunknown! Cat.", "title": "first"}
    response = await client.post(f"{BASE}/ingest", headers=headers, json=data)
    assert response.status_code == 201, response.text
    first = response.json()
    assert [part["order"] for part in first["sentences"]] == [0, 1]
    assert "".join(part["sentence"]["text"] for part in first["sentences"]) == data["text"]
    for part in first["sentences"]:
        start, end = part["span"]
        assert data["text"][start:end] == part["sentence"]["text"]
    repeated = await client.post(f"{BASE}/ingest", headers=headers, json=data)
    assert repeated.json() == first
    second = (
        await client.post(f"{BASE}/ingest", headers=headers, json={**data, "title": "second"})
    ).json()
    assert first["passage"]["id"] != second["passage"]["id"]
    assert first["sentences"][0]["sentence"]["id"] == second["sentences"][0]["sentence"]["id"]
    part = first["sentences"][0]
    occurrences = part["occurrences"]
    assert occurrences[0]["status"] == occurrences[2]["status"] == "resolved"
    assert occurrences[-1]["status"] == "unmatched"
    ambiguous = occurrences[1]
    assert ambiguous["status"] == "ambiguous"
    sentence_path = f"{BASE}/sentence/{part['sentence']['id']}"
    resolution = {"span": ambiguous["span"], "sense_id": ambiguous["candidates"][0]["sense_id"]}
    resolved = await client.put(f"{sentence_path}/occurrences", headers=headers, json=resolution)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["occurrences"][1]["status"] == "resolved"
    retried = (await client.post(f"{BASE}/ingest", headers=headers, json=data)).json()
    assert retried["sentences"][0]["occurrences"][1]["sense_id"] == resolution["sense_id"]
    for span in ([-1, 2], [0, 99999], [4, 4], [1, 4], [True, 4], ["2", 4], [2, 4, 5]):
        assert (
            await client.put(
                f"{sentence_path}/occurrences", headers=headers, json={**resolution, "span": span}
            )
        ).status_code == 422
    edge = resolved.json()["occurrences"][1]["edge_id"]
    assert (
        await client.delete(f"{sentence_path}/occurrences/{edge}", headers=headers)
    ).status_code == 204
    assert (
        await client.delete(f"{BASE}/passage/{first['passage']['id']}", headers=headers)
    ).status_code == 204
    assert (await client.get(sentence_path, headers=headers)).status_code == 200
    reading = await client.get(f"{BASE}/passage/{second['passage']['id']}/reading", headers=headers)
    assert reading.status_code == 200
    assert len(reading.json()["sentences"]) == 2


async def test_crud_auth_bounds_and_cross_user_records(
    client: AsyncClient,
    make_user: UserFactory,
) -> None:
    alice, bob = await make_user(), await make_user(role="admin")
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    assert (await client.post(f"{BASE}/ingest", json={"text": "Cat."})).status_code == 401
    for kind in ("sentence", "passage"):
        body = (
            {"text": "Cat.", "translation": {"zh": "猫"}}
            if kind == "sentence"
            else {"text": "Cat."}
        )
        created = await client.post(f"{BASE}/{kind}", headers=ah, json=body)
        assert created.status_code == 201, created.text
        path = f"{BASE}/{kind}/{created.json()['id']}"
        assert (await client.get(path, headers=ah)).json() == created.json()
        assert (await client.get(f"{BASE}/{kind}", headers=bh)).json() == []
        for method in ("GET", "PUT", "DELETE"):
            kwargs: dict[str, Any] = {"json": {"text": "Stolen"}} if method == "PUT" else {}
            assert (await client.request(method, path, headers=bh, **kwargs)).status_code == 404
        changed = await client.put(path, headers=ah, json={"text": "Bird.", "lang": "en"})
        assert changed.status_code == 200
        assert changed.json()["text"] == "Bird."
        assert (
            await client.get(f"{BASE}/{kind}", headers=ah, params={"limit": 1, "offset": 0})
        ).status_code == 200
        for query in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001}):
            assert (await client.get(f"{BASE}/{kind}", headers=ah, params=query)).status_code == 422
        assert (await client.delete(path, headers=ah)).status_code == 204
        assert (await client.get(path, headers=ah)).status_code == 404
    for text in ("", " ", "Cat.\n" * 201):
        assert (
            await client.post(f"{BASE}/ingest", headers=ah, json={"text": text})
        ).status_code == 422
    assert (await client.get(f"{BASE}/sentence/not-an-id", headers=ah)).status_code == 404


async def test_failed_ingestion_rolls_back_all_rows_and_dictionary_edges(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user()
    before = await support.counts(db, user.id)
    shared_before = await support.shared_counts(db)
    original = content.repository.resolve
    calls = 0

    async def fail(*args: Any, **kwargs: Any) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected failure after first occurrence")
        return await original(*args, **kwargs)

    monkeypatch.setattr(content.repository, "resolve", fail)
    with pytest.raises(RuntimeError, match="injected"):
        await content.ingest(db, lexicon_reader, user.id, ContentCreate(text="cat cat."))
    assert calls == 2
    assert await support.counts(db, user.id) == before
    assert await support.shared_counts(db) == shared_before
    monkeypatch.setattr(content.repository, "resolve", original)
    result = await content.ingest(db, lexicon_reader, user.id, ContentCreate(text="cat cat."))
    assert len(result.sentences[0].occurrences) == 2


async def test_cross_user_associations_not_returned_or_modified(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    make_user: UserFactory,
) -> None:
    alice, bob = await make_user(), await make_user()
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    first = (await client.post(f"{BASE}/ingest", headers=ah, json={"text": "cat."})).json()
    other = (await client.post(f"{BASE}/ingest", headers=bh, json={"text": "bank."})).json()
    sentence = first["sentences"][0]["sentence"]["id"]
    sid = decode_rid(sentence, "sentence")
    pid = decode_rid(first["passage"]["id"], "passage")
    foreign_sid = decode_rid(other["sentences"][0]["sentence"]["id"], "sentence")
    await support.foreign_part(db, alice.id, foreign_sid, pid)
    await support.foreign_part(db, bob.id, sid, pid)
    sense = decode_rid(first["sentences"][0]["occurrences"][0]["sense_id"], "sense")
    foreign_edge = await support.foreign_link(db, bob.id, sid, sense)
    reading = (
        await client.get(f"{BASE}/passage/{first['passage']['id']}/reading", headers=ah)
    ).json()
    assert len(reading["sentences"]) == 1
    sentence_path = f"{BASE}/sentence/{sentence}/occurrences"
    assert (await client.get(sentence_path, headers=bh)).status_code == 404
    assert (
        await client.put(
            sentence_path, headers=bh, json={"span": [0, 3], "sense_id": encode_rid(sense, "sense")}
        )
    ).status_code == 404
    edge_path = f"{sentence_path}/{encode_rid(foreign_edge, 'used_in')}"
    assert (await client.delete(edge_path, headers=ah)).status_code == 404
    assert (await client.delete(edge_path, headers=bh)).status_code == 404
    private = await support.private_sense(db, bob.id)
    resolution = {"span": [0, 3], "sense_id": encode_rid(private, "sense")}
    assert (await client.put(sentence_path, headers=ah, json=resolution)).status_code == 404
    # Even an edge owned by Alice cannot expose Bob's private sense.
    await support.foreign_link(db, alice.id, sid, private)
    occurrence = (await client.get(sentence_path, headers=ah)).json()["occurrences"][0]
    assert occurrence["sense_id"] != resolution["sense_id"]
    before = await support.counts(db, bob.id)
    assert (
        await client.delete(f"{BASE}/passage/{first['passage']['id']}", headers=ah)
    ).status_code == 409
    assert await support.counts(db, bob.id) == before


async def test_concurrent_retries_repeat_sentence_and_edited_row_conflict(
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    user = await make_user()
    data = ContentCreate(text="cat.\ncat.\n")
    first, second = await asyncio.gather(
        content.ingest(db, lexicon_reader, user.id, data),
        content.ingest(db, lexicon_reader, user.id, data),
    )
    assert first == second
    assert len(first.sentences) == 2
    assert first.sentences[0].sentence.id == first.sentences[1].sentence.id
    assert await support.counts(db, user.id) == {
        "sentence": 1,
        "passage": 1,
        "part_of": 2,
        "used_in": 1,
    }
    await content.update(
        db, user.id, "sentence", first.sentences[0].sentence.id, ContentCreate(text="Changed.")
    )
    from app.core.errors import AppError

    with pytest.raises(AppError) as error:
        await content.ingest(db, lexicon_reader, user.id, data)
    assert error.value.code == "content.retry_conflict"


async def test_manual_part_crud_authorizes_both_endpoints_and_preserves_gap_spans(
    client: AsyncClient,
    make_user: UserFactory,
) -> None:
    alice, bob = await make_user(), await make_user()
    ah, bh = bearer(await login(client, alice.username)), bearer(await login(client, bob.username))
    data = {"text": "cat.\ncat.\n"}
    ingested = (await client.post(f"{BASE}/ingest", headers=ah, json=data)).json()
    pid = ingested["passage"]["id"]
    edge = f"{BASE}/passage/{pid}/sentences/0"
    assert (await client.delete(edge, headers=bh)).status_code == 404
    assert (await client.delete(edge, headers=ah)).status_code == 204
    reading = (await client.get(f"{BASE}/passage/{pid}/reading", headers=ah)).json()
    assert reading["sentences"][0]["order"] == 1
    assert reading["sentences"][0]["span"] == [5, 10]
    standalone = (await client.post(f"{BASE}/sentence", headers=ah, json={"text": "cat.\n"})).json()
    assignment = {"sentence_id": standalone["id"]}
    assert (await client.put(edge, headers=bh, json=assignment)).status_code == 404
    foreign = (await client.post(f"{BASE}/sentence", headers=bh, json={"text": "cat.\n"})).json()
    assert (
        await client.put(edge, headers=ah, json={"sentence_id": foreign["id"]})
    ).status_code == 404
    assert (await client.put(edge, headers=ah, json=assignment)).status_code == 204
    assert (await client.put(edge, headers=ah, json=assignment)).status_code == 204
    reading = (await client.get(f"{BASE}/passage/{pid}/reading", headers=ah)).json()
    assert [part["order"] for part in reading["sentences"]] == [0, 1]
    assert reading["sentences"][0]["sentence"]["id"] == standalone["id"]
    assert (
        await client.put(f"{BASE}/passage/{pid}/sentences/200", headers=ah, json=assignment)
    ).status_code == 422
    assert (
        await client.put(f"{BASE}/passage/{pid}/sentences/2", headers=ah, json=assignment)
    ).status_code == 422
    mismatch = (await client.post(f"{BASE}/sentence", headers=ah, json={"text": "dog"})).json()
    assert (
        await client.put(edge, headers=ah, json={"sentence_id": mismatch["id"]})
    ).status_code == 422


@pytest.mark.parametrize("reason", ["disabled", "invalid_response", "rejected_response"])
async def test_optional_assistance_unavailable_is_offline_safe_and_private(
    client: AsyncClient,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
    reason: Any,
) -> None:
    user = await make_user()
    headers = bearer(await login(client, user.username))
    sentence = (
        await client.post(f"{BASE}/sentence", headers=headers, json={"text": "Private bank"})
    ).json()
    captured = {}

    async def unavailable(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        raise LlmUnavailable(reason)

    monkeypatch.setattr(content.llm, "generate_json", unavailable)
    response = await client.get(
        f"{BASE}/sentence/{sentence['id']}/occurrences", headers=headers, params={"assist": True}
    )
    assert response.status_code == 200
    assert response.json()["assistance"] == f"unavailable:{reason}"
    assert captured["user"] == user.id
    assert captured["inputs"]["text"] == "Private bank"
    assert "shared_sources" not in captured
    validator = captured["validate"]
    from app.domain.content import Suggestion

    assert not validator(
        Suggestion.model_validate({"resolutions": [{"span": [0, 7], "sense_id": "invented"}]})
    )
