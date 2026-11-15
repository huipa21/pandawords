from typing import Any

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid, encode_rid
from app.db.migration_store import checked_query
from app.services.lexicon import LexiconReader
from tests.api.project_import_support import (
    Account,
    Dirs,
    accounts,
    db,
    dirs,
    media_files,
    png,
    rebuild,
    seed,
    snapshot,
    test_settings,
    upload,
)

pytestmark = pytest.mark.integration
__all__ = ["accounts", "db", "dirs", "test_settings"]


async def one(db: AsyncWsSurrealConnection, query: str, **variables: Any) -> list[dict[str, Any]]:
    return (await checked_query(db, query, variables))[0]


async def test_round_trip_merges_shared_and_remaps_owned(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    dirs: Dirs,
) -> None:
    alice, bob = accounts
    seeded = await seed(client, db, alice, lexicon_reader, dirs)
    words = seeded.words
    lexeme_before = await one(db, "SELECT * FROM $l;", l=words.lexeme)
    before = await snapshot(db, alice.user)
    files_before = media_files(dirs)

    response = await upload(client, alice, seeded.archive)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["same_source"] is True and body["progress_imported"] is True
    project = decode_rid(body["project_ids"][0], "project")
    assert project != seeded.project
    assert {"memory_kept", "override_kept"} <= set(body["conflicts"])
    after = await snapshot(db, alice.user)
    shared = {k: v for k, v in after.items() if k.startswith("shared.")}
    assert shared == {k: v for k, v in before.items() if k.startswith("shared.")}
    assert await one(db, "SELECT * FROM $l;", l=words.lexeme) == lexeme_before  # not overwritten
    key = str(alice.user.id)
    grew = {t: after[f"{key}.{t}"] - before[f"{key}.{t}"] for t in ("project", "includes")}
    assert grew == {"project": 1, "includes": 4}
    assert after[f"{key}.lemma"] == before[f"{key}.lemma"]  # own lemma reused by identity
    for table in ("memory", "review_log", "override"):  # kept, no duplicate receipts
        assert after[f"{key}.{table}"] == before[f"{key}.{table}"]

    members = await one(
        db,
        "SELECT out, hidden, study_order, owner FROM includes WHERE in = $p;",
        p=project,
    )
    assert {(m["out"], m["hidden"], m.get("study_order")) for m in members} == {
        (words.lemma, False, None),
        (words.move, False, 1),
        (words.operate, True, 0),
        (seeded.lemma, False, None),
    }
    assert {m["owner"] for m in members} == {alice.user}
    tags = await one(
        db, "SELECT out FROM member_of WHERE in = $s AND owner = $u;", s=words.move, u=alice.user
    )
    new_tags = {t["out"] for t in tags} - {seeded.tag}
    assert len(new_tags) == 1
    assert (await one(db, "SELECT name, owner FROM $t;", t=new_tags.pop()))[0] == {
        "name": "Alice exam",
        "owner": alice.user,
    }
    notes = await one(db, "SELECT text FROM note WHERE target = $p;", p=project)
    assert notes == [{"text": "project note"}]
    images = await one(
        db,
        "SELECT path FROM media WHERE owner = $u AND target = $s AND kind = 'image';",
        u=alice.user,
        s=words.move,
    )
    new_files = media_files(dirs) - files_before
    assert len(images) == 2 and len(new_files) == 1
    assert new_files.pop().read_bytes() == png()

    again = await upload(client, alice, seeded.archive)  # Repeated import: another copy.
    assert again.status_code == 201, again.text
    assert again.json()["project_ids"][0] not in body["project_ids"]
    assert (await snapshot(db, alice.user))[f"{key}.project"] == after[f"{key}.project"] + 1

    hidden = await client.get(f"/api/projects/{body['project_ids'][0]}", headers=bob.headers)
    assert hidden.status_code == 404


async def test_progress_option_paths_and_isolation(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    dirs: Dirs,
) -> None:
    alice, bob = accounts
    seeded = await seed(client, db, alice, lexicon_reader, dirs)
    words = seeded.words
    alice_before = await snapshot(db, alice.user)

    # Not the exporter: the bundle's lemma identity belongs to alice -> conflict, nothing written.
    conflict = await upload(client, bob, seeded.archive, include_progress=True)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "bundle.identity_conflict"
    assert conflict.json()["problems"] == ["lemma_identity: lemma"]
    await checked_query(db, "DELETE $l;", {"l": seeded.lemma})
    await checked_query(db, "DELETE includes WHERE out = $l;", {"l": seeded.lemma})

    def receipt_source(raw: dict[str, Any]) -> None:
        log = raw["review_log"][0]
        log.update(project=None, card_after=raw["memory"][0]["card"])

    archive = rebuild(dirs, seeded.archive, receipt_source)
    first = await upload(client, bob, archive, include_progress=True)
    assert first.status_code == 201, first.text
    assert first.json()["same_source"] is False and first.json()["progress_imported"] is True
    project = decode_rid(first.json()["project_ids"][0], "project")
    memory = RecordID("memory", [bob.user, words.move])
    card = (await one(db, "SELECT introduced, stability, card_id FROM $m;", m=memory))[0]
    assert card == {"introduced": True, "stability": 3.5, "card_id": 7}
    logs = await one(
        db, "SELECT attempt_id, project, receipt FROM review_log WHERE owner = $u;", u=bob.user
    )
    assert [(log["attempt_id"], log["project"]) for log in logs] == [("alice-1", project)]
    # project=null falls back to the imported project; the receipt is rebuilt from card_after.
    receipt = logs[0]["receipt"]
    assert receipt["project_id"] == encode_rid(project, "project")
    assert receipt["memory"]["id"] == encode_rid(memory, "memory")
    assert receipt["memory"]["card"]["card_id"] == 7

    # Default for another user's bundle is off; existing memory is preserved, no duplicates.
    second = await upload(client, bob, seeded.archive)
    assert second.status_code == 201, second.text
    assert second.json()["progress_imported"] is False
    assert (await one(db, "SELECT stability FROM $m;", m=memory))[0]["stability"] == 3.5
    assert len(await one(db, "SELECT id FROM review_log WHERE owner = $u;", u=bob.user)) == 1

    # Progress off on a sense without memory creates a new card.
    await checked_query(
        db, "DELETE $m; DELETE review_log WHERE owner = $u;", {"m": memory, "u": bob.user}
    )
    third = await upload(client, bob, seeded.archive, include_progress=False)
    assert third.status_code == 201, third.text
    fresh = (await one(db, "SELECT introduced, state, last_review FROM $m;", m=memory))[0]
    assert fresh["introduced"] is False and fresh["state"] == 1 and fresh.get("last_review") is None
    assert await one(db, "SELECT id FROM review_log WHERE owner = $u;", u=bob.user) == []

    # Bob's imported rows are his own; alice's data is untouched.
    assert await snapshot(db, alice.user) == {
        **alice_before,
        f"{alice.user.id}.lemma": alice_before[f"{alice.user.id}.lemma"] - 1,
        f"{alice.user.id}.includes": alice_before[f"{alice.user.id}.includes"] - 1,
    }
    for table in ("includes", "member_of", "media", "note", "tag", "project"):
        rows = await one(
            db, "SELECT owner FROM type::table($t) WHERE owner = $u;", t=table, u=bob.user
        )
        assert rows, table
    bob_media = await one(db, "SELECT path, kind FROM media WHERE owner = $u;", u=bob.user)
    assert {m["kind"] for m in bob_media} == {"image"}  # shared audio exists: merged, not copied
    alice_view = await client.get(
        f"/api/projects/{encode_rid(project, 'project')}", headers=alice.headers
    )
    assert alice_view.status_code == 404
