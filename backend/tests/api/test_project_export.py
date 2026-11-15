import hashlib
import tarfile
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from httpx import AsyncClient, Response
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.config import Settings
from app.core.errors import BundleError
from app.core.record_ids import decode_rid, encode_rid
from app.db.dictionary_schema_test_support import relate
from app.db.migration_store import checked_query
from app.db.project_schema_test_support import put_override
from app.domain.bundle_records import LexemeRecord, TagRecord
from app.domain.bundle_refs import shared_ref
from app.domain.identity import user_key
from app.services import project_export
from app.services.bundle_io import LoadedBundle, load_bundle
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.api.project_export_support import (
    ALICE_IMAGE,
    SHARED_AUDIO,
    dictionary,
    foreign_account,
    include,
    media,
    owned,
    progress,
    store_file,
)
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration
PROJECT_FORMATS = frozenset({"pandawords.project"})


@dataclass
class Dirs:
    root: Path
    media: Path
    work: Path


@pytest.fixture
def test_settings(job_settings: Settings) -> Settings:
    return job_settings


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


@pytest.fixture(autouse=True)
def dirs(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Dirs]:
    with TemporaryDirectory(dir=Path.cwd(), prefix=".project-export-") as directory:
        root = Path(directory)
        found = Dirs(root, root / "media", root / "work")
        found.media.mkdir()
        monkeypatch.setattr(test_settings, "media_dir", found.media)
        monkeypatch.setattr(test_settings, "bundle_work_dir", found.work)
        yield found


@dataclass
class Account:
    user: RecordID
    headers: dict[str, str]


@pytest.fixture
async def accounts(client: AsyncClient, make_user: UserFactory) -> AsyncIterator[list[Account]]:
    found: list[Account] = []
    for _ in range(2):
        created = await make_user()
        headers = bearer(await login(client, created.username))
        found.append(Account(RecordID("user", user_key(created.id)), headers))
    yield found


async def new_project(client: AsyncClient, account: Account, name: str) -> RecordID:
    response = await client.post("/api/projects", headers=account.headers, json={"name": name})
    assert response.status_code == 201, response.text
    return decode_rid(response.json()["id"], "project")


async def download(
    client: AsyncClient, account: Account, project: RecordID, dirs: Dirs
) -> tuple[Response, LoadedBundle]:
    response = await client.get(
        f"/api/projects/{encode_rid(project, 'project')}/export", headers=account.headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/gzip"
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    assert list(dirs.work.iterdir()) == []  # Archive directory is removed after sending.
    archive = dirs.root / f"{project.id}.tar.gz"
    archive.write_bytes(response.content)
    return response, load_bundle(archive, dirs.root, expected_formats=PROJECT_FORMATS)


def members(bundle: LoadedBundle) -> list[str]:
    return [entry.path for entry in bundle.archive.manifest.entries]


async def test_export_tree_overlays_progress_media_and_isolation(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    dirs: Dirs,
) -> None:
    alice, bob = accounts
    words = await dictionary(db, lexicon_reader)
    project = await new_project(client, alice, "IELTS 雅思/../x")
    other = await new_project(client, alice, "Other")
    await include(db, alice.user, project, words.lemma)
    await include(db, alice.user, project, words.move, study_order=1)
    await include(db, alice.user, project, words.operate, hidden=True, study_order=0)
    await include(db, alice.user, other, words.flow)
    await foreign_account(db, words, bob.user, await new_project(client, bob, "Bob"), dirs.media)
    await put_override(db, alice.user, words.move, {"definition": "My meaning"})
    await put_override(db, alice.user, words.flow, {"definition": "Other project only"})
    await owned(db, "note", alice.user, target=words.move, kind="mnemonic", text="run = 润")
    await owned(db, "note", alice.user, target=project, kind="note", text="project note")
    await owned(db, "note", alice.user, target=other, kind="note", text="OTHER-PROJECT-NOTE")
    tag = await owned(db, "tag", alice.user, kind="custom", name="Alice exam")
    await relate(db, "member_of", words.move, tag, {"owner": alice.user})
    image = store_file(dirs.media, "image/aa/alice.png", ALICE_IMAGE)
    await media(db, alice.user, words.move, image)
    audio = store_file(dirs.media, "audio/cc/run.mp3", SHARED_AUDIO)
    shared_audio = await media(db, None, words.lexeme, audio, kind="audio")
    lost_audio = await media(db, None, words.lexeme, "audio/ff/lost.mp3", kind="audio")
    pron: list[Value] = [
        {"accent": "US", "ipa": "/rʌn/", "audio": shared_audio},
        {"accent": "UK", "ipa": "/rʌn/", "audio": lost_audio},
    ]
    await checked_query(
        db, "UPDATE $lexeme SET pron = $pron;", {"lexeme": words.lexeme, "pron": pron}
    )
    await media(db, alice.user, words.operate, "image/dd/missing.png")
    (dirs.media / "image" / "ee" / "dir.png").mkdir(parents=True)
    await media(db, alice.user, words.operate, "image/ee/dir.png")
    await media(db, alice.user, words.operate, "../outside.png")
    await progress(db, alice.user, words.move, project, "alice-1")
    await progress(db, alice.user, words.flow, other, "alice-other")

    foreign = await client.get(
        f"/api/projects/{encode_rid(project, 'project')}/export", headers=bob.headers
    )
    assert foreign.status_code == 404
    assert (
        await client.get(f"/api/projects/{encode_rid(project, 'project')}/export")
    ).status_code == 401

    response, bundle = await download(client, alice, project, dirs)
    try:
        assert response.headers["x-pandawords-skipped-media"] == "4"
        lexeme = bundle.index.records[shared_ref("lexeme", words.lexeme.id)]
        assert isinstance(lexeme, LexemeRecord)
        audio_refs = [p.audio for p in lexeme.pron]
        assert audio_refs[0] is not None and audio_refs[1] is None
        assert bundle.index.media[audio_refs[0]].kind == "audio"
        assert "IELTS" in response.headers["content-disposition"]
        data = bundle.data
        assert [p.name for p in data.projects] == ["IELTS 雅思/../x"]
        move, operate = shared_ref("sense", words.move.id), shared_ref("sense", words.operate.id)
        flow = shared_ref("sense", words.flow.id)
        lemma = shared_ref("lemma", words.lemma.id)
        membership = {i.target: (i.hidden, i.study_order) for i in data.includes}
        assert membership == {lemma: (False, None), move: (False, 1), operate: (True, 0)}
        refs = set(bundle.index.records)
        assert {move, operate, lemma, shared_ref("lexeme", words.lexeme.id)} <= refs
        assert flow not in refs  # Unselected sense and other project's membership.
        assert [(o.target, o.fields) for o in data.overrides] == [
            (move, {"definition": "My meaning"})
        ]
        assert sorted(n.text for n in data.notes) == ["project note", "run = 润"]
        tags = [r for r in data.records if isinstance(r, TagRecord) and r.owner == "owned"]
        assert [t.name for t in tags] == ["Alice exam"]
        assert {(e.table, e.to) for e in data.edges if e.owner == "owned"} == {
            ("member_of", tags[0].ref)
        }
        has_sense = {e.to for e in data.edges if e.table == "has_sense"}
        assert has_sense == {move, operate}
        assert [(m.sense, m.introduced) for m in data.memory] == [(move, True)]
        assert [(log.attempt_id, log.project) for log in data.review_log] == [
            ("alice-1", data.projects[0].ref)
        ]
        assert sorted((m.kind, m.owner) for m in data.media) == [
            ("audio", "shared"),
            ("image", "owned"),
        ]
        for item in data.media:
            content = bundle.media_path(item.file).read_bytes()
            assert content in {ALICE_IMAGE, SHARED_AUDIO}
            assert item.file == f"media/{hashlib.sha256(content).hexdigest()}" + (
                ".png" if item.kind == "image" else ".mp3"
            )
        assert bundle.archive.manifest.attribution
        raw = bundle.archive.read_bytes("data.json").decode()
        for secret in ("BOB-SECRET", "OTHER-PROJECT", "Other project only", "alice-other"):
            assert secret not in raw
        for leak in ("image/aa", "audio/cc", str(dirs.media), str(alice.user.id)):
            assert leak not in raw
        assert str(project.id) not in raw
        assert sorted(members(bundle))[0:1] == ["data.json"]
        assert all(p == "data.json" or p.startswith("media/") for p in members(bundle))
    finally:
        bundle.close()
    with tarfile.open(dirs.root / f"{project.id}.tar.gz") as archive:
        names = archive.getnames()
        assert names[0] == "manifest.json" and len(names) == 4


async def test_export_empty_and_shared_only_projects(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    dirs: Dirs,
) -> None:
    alice, bob = accounts
    empty = await new_project(client, alice, "Empty")
    _, bundle = await download(client, alice, empty, dirs)
    try:
        data = bundle.data
        assert len(data.projects) == 1 and data.projects[0].name == "Empty"
        assert not (data.records or data.edges or data.includes or data.media or data.memory)
        assert members(bundle) == ["data.json"]
        assert bundle.archive.manifest.attribution == []
    finally:
        bundle.close()

    words = await dictionary(db, lexicon_reader)
    shared = await new_project(client, alice, "Shared")
    await include(db, alice.user, shared, words.lemma)
    await foreign_account(db, words, bob.user, await new_project(client, bob, "Bob"), dirs.media)
    _, bundle = await download(client, alice, shared, dirs)
    try:
        data = bundle.data
        assert data.records and all(r.owner == "shared" for r in data.records)
        assert data.edges and all(e.owner == "shared" for e in data.edges)
        assert not any(e.table == "has_sense" for e in data.edges)  # No sense selected.
        assert not (data.notes or data.overrides or data.memory or data.review_log or data.media)
        assert bundle.archive.manifest.attribution
    finally:
        bundle.close()


async def test_export_failure_removes_partial_archive(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    dirs: Dirs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = accounts[0]
    words = await dictionary(db, lexicon_reader)
    project = await new_project(client, alice, "Fails")
    await include(db, alice.user, project, words.move)

    def broken(destination: Path, *_: object, **__: object) -> None:
        destination.with_name(".partial").write_bytes(b"partial")
        raise BundleError("integrity", "archive")

    monkeypatch.setattr(project_export, "export_bundle", broken)
    response = await client.get(
        f"/api/projects/{encode_rid(project, 'project')}/export", headers=alice.headers
    )
    assert response.status_code == 422
    assert response.json()["code"] == "bundle.integrity"
    assert list(dirs.work.iterdir()) == []
