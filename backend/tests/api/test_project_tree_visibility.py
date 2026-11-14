from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import create, relate
from app.db.project_schema_test_support import owned
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


async def test_legacy_duplicates_custom_senses_and_foreign_marker_conflict(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
) -> None:
    alice, bob = await make_user(), await make_user()
    user, other = RecordID("user", user_key(alice.id)), RecordID("user", user_key(bob.id))
    headers = bearer(await login(client, alice.username))
    project = (await client.post("/api/projects", headers=headers, json={"name": "Legacy"})).json()
    project_id = decode_rid(project["id"], "project")
    entry = await materialize_lemma(
        db,
        lexicon_reader,
        "run",
        selected_senses=[sense_key("en", "run", "verb", source_sense_id="run-move")],
    )
    lemma = decode_rid(entry.lemma_id, "lemma")
    lexeme = RecordID("lexeme", lexeme_key("en", "run", "verb"))
    sense = decode_rid(entry.selected_sense_ids[0], "sense")
    content = {"owner": user, "hidden": False, "added_at": NOW}
    await relate(db, "includes", project_id, lemma, content)
    await relate(db, "includes", project_id, sense, content)
    await relate(db, "includes", project_id, sense, {**content, "hidden": True})
    url = f"/api/projects/{project['id']}/tree"
    assert (await client.get(url, headers=headers)).json()["items"][0]["lexemes"] == []
    before = await owned(db, "includes", user)
    result = await client.patch(
        f"{url}/sense/{entry.selected_sense_ids[0]}/visibility",
        headers=headers,
        json={"hidden": False},
    )
    assert result.status_code == 200, result.text
    after = await owned(db, "includes", user)
    assert {row["id"] for row in before} == {row["id"] for row in after}
    for row in after:
        assert row["added_at"] == NOW and not row["hidden"]
    # An owner's custom sense participates only through their own safe edge/selection.
    custom = RecordID("sense", uuid4().hex)
    await create(
        db,
        custom,
        {
            "owner": user,
            "definition": "Personal meaning",
            "gloss": {"zh": "个人"},
            "register": [],
            "domain": [],
            "examples": [],
            "rank": 99,
            "common": False,
            "source": "custom",
        },
    )
    await relate(db, "has_sense", lexeme, custom, {"owner": user, "rank": 99})
    await relate(db, "includes", project_id, custom, content)
    tree = (await client.get(url, headers=headers)).json()
    assert [s["sense"]["id"] for s in tree["items"][0]["lexemes"][0]["senses"]] == [
        entry.selected_sense_ids[0],
        encode_rid(custom, "sense"),
    ]
    foreign_marker = RecordID("includes", [project_id, lexeme])
    await db.relate(
        project_id,
        foreign_marker,
        lexeme,
        {"owner": other, "hidden": True, "added_at": NOW},
    )
    foreign_before = await owned(db, "includes", other)
    # Foreign includes flags do not suppress the requester's group.
    assert (await client.get(url, headers=headers)).json() == tree
    conflict = await client.patch(
        f"{url}/lexeme/{encode_rid(lexeme, 'lexeme')}/visibility",
        headers=headers,
        json={"hidden": True},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "project.membership_conflict"
    assert await owned(db, "includes", other) == foreign_before
    assert (await client.get(url, headers=headers)).json() == tree
