import io
import tarfile
from typing import Any

import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db import bundle_import as import_repository
from app.domain.bundle_refs import shared_ref
from app.services import bundle_import as import_service
from app.services.lexicon import LexiconReader
from tests.api.project_export_support import ALICE_IMAGE, owned
from tests.api.project_import_support import (
    Account,
    Dirs,
    accounts,
    db,
    dirs,
    export,
    media_files,
    rebuild,
    seed,
    snapshot,
    test_settings,
    upload,
)

pytestmark = pytest.mark.integration
__all__ = ["accounts", "db", "dirs", "test_settings"]


def tar_with(name: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


async def rejected(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    account: Account,
    dirs: Dirs,
    content: bytes,
    status: int,
) -> dict[str, Any]:
    before, files = await snapshot(db, account.user), media_files(dirs)
    response = await upload(client, account, content)
    assert response.status_code == status, response.text
    assert await snapshot(db, account.user) == before
    assert media_files(dirs) == files
    assert not dirs.work.exists() or list(dirs.work.iterdir()) == []
    body = response.json()
    assert body["code"].startswith("bundle.") and "stage" in body
    assert str(dirs.root) not in response.text
    return body


async def test_malformed_traversal_and_oversized_uploads_write_nothing(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    test_settings: Settings,
    dirs: Dirs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = accounts[0]
    assert (await client.post("/api/projects/import", content=b"x")).status_code == 401
    await rejected(client, db, alice, dirs, b"not a gzip archive", 422)
    body = await rejected(client, db, alice, dirs, tar_with("../evil.json", b"{}"), 422)
    assert body["stage"] == "archive"
    assert not (dirs.root / "evil.json").exists() and not (dirs.work / "evil.json").exists()
    await rejected(client, db, alice, dirs, b"", 422)
    monkeypatch.setattr(test_settings, "bundle_import_max_bytes", 16)
    body = await rejected(client, db, alice, dirs, b"x" * 64, 413)
    assert (body["code"], body["stage"]) == ("bundle.too_large", "upload")


async def test_invalid_media_and_forged_identities_write_nothing(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    test_settings: Settings,
    dirs: Dirs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice, bob = accounts
    seeded = await seed(client, db, alice, lexicon_reader, dirs)
    with monkeypatch.context() as patch:
        patch.setattr(test_settings, "audio_max_bytes", 4)
        body = await rejected(client, db, alice, dirs, seeded.archive, 422)
    assert (body["code"], body["stage"]) == ("bundle.invalid_media", "media")
    assert [p.split(":")[0] for p in body["problems"]] == ["media_size"]
    (dirs.media / "image" / "aa" / "alice.png").write_bytes(ALICE_IMAGE)  # not a real PNG
    fake = await export(client, alice, seeded.project)
    body = await rejected(client, db, alice, dirs, fake, 422)
    assert [p.split(":")[0] for p in body["problems"]] == ["media_content"]

    # A "shared" ref that points at another user's private row must not be merged into.
    secret = await owned(db, "tag", bob.user, kind="custom", name="BOB-SECRET")

    def forge(raw: dict[str, Any]) -> None:
        tag = next(r for r in raw["records"] if r["table"] == "tag")
        old, new = tag["ref"], shared_ref("tag", secret.id)
        tag.update(ref=new, owner="shared")
        for edge in raw["edges"]:
            if edge["to"] == old:
                edge["to"] = new

    forged = rebuild(dirs, seeded.archive, forge)
    body = await rejected(client, db, alice, dirs, forged, 409)
    assert body["code"] == "bundle.identity_conflict"
    assert body["problems"] == ["shared_identity: tag"]
    assert "BOB-SECRET" not in str(body)


@pytest.mark.parametrize("target", ["write_plan", "copy_files"])
async def test_database_or_file_failure_rolls_back_rows_and_media(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    dirs: Dirs,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    alice = accounts[0]
    seeded = await seed(client, db, alice, lexicon_reader, dirs)
    original_write = import_repository.write_plan
    original_copy = import_service._copy_files  # pyright: ignore[reportPrivateUsage]

    async def failing_write(*args: Any) -> None:
        await original_write(*args)
        raise RuntimeError("disk full")

    def failing_copy(*args: Any) -> None:
        original_copy(*args)
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        if target == "write_plan":
            patch.setattr(import_repository, "write_plan", failing_write)
        else:
            patch.setattr(import_service, "_copy_files", failing_copy)
        body = await rejected(client, db, alice, dirs, seeded.archive, 500)
    assert (body["code"], body["stage"]) == ("bundle.apply_failed", "apply")
    assert "disk full" not in str(body)
    assert (await upload(client, alice, seeded.archive)).status_code == 201
