import asyncio
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

import pytest
from httpx import AsyncClient
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError
from app.core.record_ids import decode_rid, encode_rid
from app.db import media_test_support as support
from app.domain.media import MediaCreate
from app.services import media
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def media_directory(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    with TemporaryDirectory(dir=Path.cwd(), prefix=".media-api-") as directory:
        root = Path(directory)
        monkeypatch.setattr(test_settings, "media_dir", root)
        yield root


@pytest.mark.parametrize("app_env", ["development", "production"])
async def test_media_access_isolation_and_target_visibility(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    test_settings: Settings,
    app_env: Literal["development", "production"],
) -> None:
    test_settings.app_env = app_env
    owner, other = await make_user(), await make_user()
    owner_headers = bearer(await login(client, owner.username))
    other_headers = bearer(await login(client, other.username))
    shared_target = await support.target(db)
    private_target = await support.target(db, owner.id)

    async def store(target: RecordID, user: str | None = None) -> str:
        result = await media.store(
            db,
            test_settings,
            MediaCreate(
                target=target,
                owner=user,
                kind="audio",
                mime="audio/mpeg",
                source="wiktionary",
                attribution="CC BY-SA example",
                accent="US",
            ),
            b"recording",
        )
        metadata = await media.read(db, test_settings, result.id, owner.id)
        assert metadata == result
        assert "path" not in result.model_dump()
        return result.id

    shared = await store(shared_target)
    private = await store(private_target, owner.id)
    private_shared_target = await store(shared_target, owner.id)
    for rid, headers in (
        (shared, owner_headers),
        (shared, other_headers),
        (private, owner_headers),
        (private_shared_target, owner_headers),
    ):
        response = await client.get(f"/api/media/{rid}", headers=headers)
        assert response.status_code == 200
        assert response.content == (b"recording" if app_env == "development" else b"")
        assert response.headers["x-accel-redirect"].startswith("/_media/audio/")
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert str(test_settings.media_dir) not in str(response.headers)
    assert (await client.get(f"/api/media/{shared}")).status_code == 401
    for rid in (private, private_shared_target, "invalid", encode_rid(RecordID("tag", "x"), "tag")):
        response = await client.get(f"/api/media/{rid}", headers=other_headers)
        assert response.status_code == 404
        assert response.json()["code"] == "media.not_found"
        assert str(test_settings.media_dir) not in response.text

    # Metadata alone cannot confer visibility to another user's target.
    await support.change(db, decode_rid(shared, "media"), {"target": private_target})
    assert (await client.get(f"/api/media/{shared}", headers=other_headers)).status_code == 404
    assert (await client.get(f"/api/media/{shared}", headers=owner_headers)).status_code == 200
    with pytest.raises(AppError) as error:
        await store(private_target)
    assert error.value.status == 404
    await support.remove(db, private_target)
    assert (await client.get(f"/api/media/{private}", headers=owner_headers)).status_code == 404


async def test_missing_corrupt_media_and_persistence_cleanup(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    test_settings: Settings,
    media_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await make_user()
    headers = bearer(await login(client, owner.username))
    target = await support.target(db)
    data = MediaCreate(target=target, kind="image", mime="image/png", source="pixabay")
    stored = await media.store(db, test_settings, data, b"image")
    path = (await asyncio.to_thread(lambda: list(media_directory.rglob("*.png"))))[0]
    assert await asyncio.to_thread(path.read_bytes) == b"image"
    await asyncio.to_thread(path.unlink)
    response = await client.get(f"/api/media/{stored.id}", headers=headers)
    assert response.status_code == 404
    assert "path" not in response.text
    for changes in (
        {"path": "../secret.png"},
        {"mime": "text/html"},
        {"path": "image/test.mp3", "mime": "image/png"},
    ):
        await support.change(db, decode_rid(stored.id, "media"), changes)
        assert (await client.get(f"/api/media/{stored.id}", headers=headers)).status_code == 404
    with pytest.raises(AppError) as error:
        await media.store(db, test_settings, data, b"")
    assert error.value.status == 422

    async def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("persistence failed")

    monkeypatch.setattr(media.repository, "create", fail)
    with pytest.raises(RuntimeError, match="persistence failed"):
        await media.store(db, test_settings, data, b"orphan")
    assert not await asyncio.to_thread(lambda: list(media_directory.rglob("*.png")))
