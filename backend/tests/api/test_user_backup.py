import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.record_ids import decode_rid
from app.domain.auth import UserPreferences
from app.services.lexicon import LexiconReader
from tests.api.project_export_support import SHARED_AUDIO
from tests.api.project_import_support import (
    Account,
    Dirs,
    accounts,
    db,
    dirs,
    media_files,
    png,
    snapshot,
    test_settings,
)
from tests.api.user_backup_support import (
    PREFS,
    account_row,
    backup,
    drop_owned_lemmas,
    open_user,
    rebuild_user,
    restore,
    rows,
    seed_user,
    set_prefs,
    wipe,
)

pytestmark = pytest.mark.integration
__all__ = ["accounts", "db", "dirs", "test_settings"]
DEFAULTS: dict[str, Value] = dict(UserPreferences().model_dump())
CHANGED = sorted(key for key, value in PREFS.items() if DEFAULTS[key] != value)
ACCOUNT_FIELDS = ("username", "password_hash", "role", "disabled", "must_change_password")


async def test_backup_contents_round_trip_and_repeat(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    dirs: Dirs,
) -> None:
    alice = accounts[0]
    seeded, _ = await seed_user(client, db, alice, lexicon_reader, dirs)
    account = await account_row(db, alice.user)
    archive = await backup(client, alice)
    for secret in (account["username"], account["password_hash"], str(alice.user.id)):
        assert secret.encode() not in archive
    bundle = open_user(dirs, archive)
    try:
        data = bundle.data
        assert bundle.archive.manifest.source is not None
        assert sorted(p.name for p in data.projects) == ["Second", "Source"]
        assert len(data.includes) == 5 and len(data.notes) == 2 and len(data.overrides) == 1
        assert [m.kind for m in data.media].count("image") == 1
        assert len(data.memory) == 1 and [log.attempt_id for log in data.review_log] == ["alice-1"]
        assert data.preferences is not None
        assert data.preferences.model_dump() == {**PREFS, "source_lang": "zh", "target_lang": "en"}
    finally:
        bundle.close()

    # Lose everything (preferences back to defaults), then restore with the default options.
    before = await snapshot(db, alice.user)
    await wipe(db, alice.user)
    await set_prefs(db, alice.user, DEFAULTS)
    for path in media_files(dirs):
        if path.read_bytes() != SHARED_AUDIO:  # shared audio stays with its shared row
            path.unlink()
    response = await restore(client, alice, archive)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["already_restored"] is False and body["same_source"] is True
    assert body["progress_imported"] is True and body["conflicts"] == []
    assert body["preferences_restored"] == CHANGED and body["preferences_kept"] == []
    assert await snapshot(db, alice.user) == before
    restored = await account_row(db, alice.user)
    assert restored["prefs"] == PREFS
    assert {k: restored[k] for k in ACCOUNT_FIELDS} == {k: account[k] for k in ACCOUNT_FIELDS}

    projects = await rows(db, "SELECT id, name FROM project WHERE owner = $u;", u=alice.user)
    by_name = {p["name"]: p["id"] for p in projects}
    assert {decode_rid(i, "project") for i in body["project_ids"]} == set(by_name.values())
    members = await rows(
        db, "SELECT out, hidden, study_order FROM includes WHERE in = $p;", p=by_name["Source"]
    )
    words = seeded.words
    assert {(m["out"], m["hidden"], m.get("study_order")) for m in members} >= {
        (words.move, False, 1),
        (words.operate, True, 0),
    }
    card = await rows(db, "SELECT stability, introduced FROM memory WHERE owner = $u;", u=alice.user)
    assert card == [{"stability": 3.5, "introduced": True}]
    logs = await rows(db, "SELECT attempt_id, project FROM review_log WHERE owner = $u;", u=alice.user)
    assert logs == [{"attempt_id": "alice-1", "project": by_name["Source"]}]
    assert sorted(p.read_bytes() for p in media_files(dirs)) == sorted([png(), SHARED_AUDIO])

    # Repeating the same restore is a no-op that reports the earlier result.
    files = media_files(dirs)
    again = await restore(client, alice, archive)
    assert again.status_code == 200, again.text
    assert again.json() == {**body, "already_restored": True}
    assert await snapshot(db, alice.user) == before and media_files(dirs) == files

    # Once all restored projects are gone the backup can be restored again; existing memory,
    # history and customized preferences are kept rather than overwritten or duplicated.
    await rows(db, "DELETE project WHERE owner = $u;", u=alice.user)
    await set_prefs(db, alice.user, {**PREFS, "theme": "light"})
    third = (await restore(client, alice, archive)).json()
    assert third["already_restored"] is False
    assert {"memory_kept", "override_kept", "preference_kept"} <= set(third["conflicts"])
    assert third["preferences_kept"] == ["theme"]
    after = await snapshot(db, alice.user)
    key = str(alice.user.id)
    assert after[f"{key}.project"] == 2
    for table in ("memory", "review_log", "override", "lemma"):
        assert after[f"{key}.{table}"] == before[f"{key}.{table}"], table
    assert (await account_row(db, alice.user))["prefs"]["theme"] == "light"


async def test_restore_into_other_user_remaps_and_isolates(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    dirs: Dirs,
) -> None:
    alice, bob = accounts
    await seed_user(client, db, alice, lexicon_reader, dirs)
    archive = await backup(client, alice)
    alice_before = await snapshot(db, alice.user)
    alice_account = await account_row(db, alice.user)
    bob_account = await account_row(db, bob.user)
    files_before = media_files(dirs)
    bob_before = await snapshot(db, bob.user)

    # Alice's own lemma text is globally unique: conflict, nothing written.
    conflict = await restore(client, bob, archive)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["problems"] == ["lemma_identity: lemma"]
    assert await snapshot(db, bob.user) == bob_before
    assert media_files(dirs) == files_before

    portable = rebuild_user(dirs, archive, drop_owned_lemmas)
    response = await restore(client, bob, portable)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["same_source"] is False and body["progress_imported"] is True
    assert body["preferences_restored"] == CHANGED

    for table in ("project", "includes", "note", "tag", "member_of", "media", "memory"):
        owners = await rows(db, "SELECT VALUE owner FROM type::table($t) WHERE owner = $u;",
                            t=table, u=bob.user)
        assert owners, table
    logs = await rows(db, "SELECT attempt_id, memory FROM review_log WHERE owner = $u;", u=bob.user)
    assert [log["attempt_id"] for log in logs] == ["alice-1"]
    assert logs[0]["memory"].id[0] == bob.user
    bob_projects = await rows(db, "SELECT VALUE id FROM project WHERE owner = $u;", u=bob.user)
    for project in bob_projects:
        members = await rows(db, "SELECT VALUE owner FROM includes WHERE in = $p;", p=project)
        assert set(members) == {bob.user}

    assert await snapshot(db, alice.user) == alice_before
    assert await account_row(db, alice.user) == alice_account
    bob_after = await account_row(db, bob.user)
    assert {k: bob_after[k] for k in ACCOUNT_FIELDS} == {k: bob_account[k] for k in ACCOUNT_FIELDS}
    assert bob_after["prefs"] == PREFS
    assert files_before <= media_files(dirs)
    view = await client.get(f"/api/projects/{body['project_ids'][0]}", headers=alice.headers)
    assert view.status_code == 404
    alice_backup = open_user(dirs, await backup(client, alice))
    try:
        assert len(alice_backup.data.projects) == 2  # bob's copy never enters alice's backup
    finally:
        alice_backup.close()

