import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.errors import BundleError
from app.db import user_restore as restore_repository
from app.services import user_backup as backup_service
from app.services.lexicon import LexiconReader
from tests.api.project_import_support import (
    Account,
    Dirs,
    accounts,
    db,
    dirs,
    media_files,
    snapshot,
    test_settings,
)
from tests.api.user_backup_support import backup, restore, seed_user, wipe

pytestmark = pytest.mark.integration
__all__ = ["accounts", "db", "dirs", "test_settings"]


async def rejected(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    account: Account,
    dirs: Dirs,
    content: bytes,
    status: int,
) -> dict[str, Any]:
    before, files = await snapshot(db, account.user), media_files(dirs)
    response = await restore(client, account, content)
    assert response.status_code == status, response.text
    assert await snapshot(db, account.user) == before
    assert media_files(dirs) == files
    assert not dirs.work.exists() or list(dirs.work.iterdir()) == []
    return response.json()


async def test_invalid_oversized_and_wrong_format_write_nothing(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    test_settings: Settings,
    dirs: Dirs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice, bob = accounts
    assert (await client.get("/api/me/backup")).status_code == 401
    assert (await client.post("/api/me/restore", content=b"x")).status_code == 401
    seeded, _ = await seed_user(client, db, alice, lexicon_reader, dirs)
    archive = await backup(client, alice)

    body = await rejected(client, db, bob, dirs, seeded.archive, 422)  # a project bundle
    assert body["code"] == "bundle.unexpected_format"
    await rejected(client, db, bob, dirs, b"not a gzip archive", 422)
    with monkeypatch.context() as patch:
        patch.setattr(test_settings, "audio_max_bytes", 4)
        body = await rejected(client, db, alice, dirs, archive, 422)
    assert (body["code"], body["stage"]) == ("bundle.invalid_media", "media")
    monkeypatch.setattr(test_settings, "bundle_import_max_bytes", 16)
    body = await rejected(client, db, alice, dirs, archive, 413)
    assert (body["code"], body["stage"]) == ("bundle.too_large", "upload")


async def test_interrupted_restore_rolls_back_and_retry_is_safe(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    accounts: list[Account],
    lexicon_reader: LexiconReader,
    dirs: Dirs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = accounts[0]
    await seed_user(client, db, alice, lexicon_reader, dirs)
    archive = await backup(client, alice)
    await wipe(db, alice.user)
    original = restore_repository.write_receipt

    async def interrupted(*args: Any) -> None:
        await original(*args)
        raise RuntimeError("connection lost")

    with monkeypatch.context() as patch:
        patch.setattr(restore_repository, "write_receipt", interrupted)
        body = await rejected(client, db, alice, dirs, archive, 500)
    assert (body["code"], body["stage"]) == ("bundle.apply_failed", "apply")
    assert "connection lost" not in str(body)

    # Concurrent retries: exactly one restore applies, the other reports the receipt or fails
    # cleanly; either way nothing is duplicated.
    first, second = await asyncio.gather(
        restore(client, alice, archive), restore(client, alice, archive)
    )
    statuses = sorted([first.status_code, second.status_code])
    assert statuses[0] == 200 and statuses[1] in {200, 500}, (first.text, second.text)
    flags = [r.json().get("already_restored") for r in (first, second) if r.status_code == 200]
    assert flags.count(False) == 1
    key = str(alice.user.id)
    counts = await snapshot(db, alice.user)
    assert (counts[f"{key}.project"], counts[f"{key}.review_log"]) == (2, 1)
    again = await restore(client, alice, archive)
    assert again.json()["already_restored"] is True
    assert await snapshot(db, alice.user) == counts


async def test_interrupted_backup_leaves_no_archive(
    client: AsyncClient,
    accounts: list[Account],
    dirs: Dirs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(destination: Path, *_: object, **__: object) -> None:
        destination.with_name(".partial").write_bytes(b"partial")
        raise BundleError("integrity", "archive")

    empty = await backup(client, accounts[1])  # no projects or rows: preferences only
    restored = await restore(client, accounts[1], empty)
    assert restored.status_code == 200, restored.text
    assert restored.json()["project_ids"] == [] and restored.json()["created"] == {}

    monkeypatch.setattr(backup_service, "export_bundle", broken)
    response = await client.get("/api/me/backup", headers=accounts[0].headers)
    assert response.status_code == 422
    assert response.json()["code"] == "bundle.integrity"
    assert list(dirs.work.iterdir()) == []
