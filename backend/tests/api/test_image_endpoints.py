import asyncio
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from httpx import AsyncClient
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import encode_rid
from app.db import media_test_support as support
from app.services import images, media
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory
from tests.unit.test_image_validation import picture

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def image_directory(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    with TemporaryDirectory(dir=Path.cwd(), prefix=".image-api-") as directory:
        root = Path(directory)
        monkeypatch.setattr(test_settings, "media_dir", root)
        yield root


async def test_image_api_owner_shared_foreign_and_delete(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    test_settings: Settings,
) -> None:
    owner, other = await make_user(), await make_user()
    headers = bearer(await login(client, owner.username))
    foreign_headers = bearer(await login(client, other.username))
    target = await support.sense(db)
    private = await support.sense(db, owner.id)
    path = f"/api/images/senses/{encode_rid(target, 'sense')}"
    private_path = f"/api/images/senses/{encode_rid(private, 'sense')}"
    content = picture()
    upload_headers = {**headers, "Content-Type": "image/png", "request-id": "upload-request-0001"}
    assert (await client.get(path)).status_code == 401
    assert (await client.get("/api/images/pixabay/search?q=cat")).status_code == 401
    assert (
        await client.post(
            f"{path}/pixabay",
            json={
                "request_id": "unauthorized-0001",
                "search_id": "a" * 64,
                "result_id": 1,
            },
        )
    ).status_code == 401
    assert (await client.get("/api/images/senses/not-valid", headers=headers)).status_code == 404
    assert (await client.get(private_path, headers=foreign_headers)).status_code == 404
    assert (
        await client.post(
            private_path, headers={**upload_headers, **foreign_headers}, content=content
        )
    ).status_code == 404
    uploaded = await client.post(path, headers=upload_headers, content=content)
    assert uploaded.status_code == 200, uploaded.text
    image = uploaded.json()
    assert image["source"] == "upload" and "path" not in image
    assert (await client.get(path, headers=headers)).json() == [image]
    assert (await client.get(path, headers=foreign_headers)).json() == []
    assert (
        await client.get(f"/api/media/{image['id']}", headers=foreign_headers)
    ).status_code == 404
    delivered = await client.get(f"/api/media/{image['id']}", headers=headers)
    assert delivered.content == content
    assert (await client.post(path, headers=upload_headers, content=content)).json() == image
    assert (
        await client.post(path, headers=upload_headers, content=picture(size=(5, 5)))
    ).status_code == 409
    delete = f"{path}/{image['id']}"
    assert (await client.delete(delete, headers=foreign_headers)).status_code == 404
    assert (await client.delete(delete, headers=headers)).status_code == 204
    assert not list(test_settings.media_dir.rglob("*.png"))
    assert (await client.get(f"/api/media/{image['id']}", headers=headers)).status_code == 404
    assert (await client.post(path, headers=upload_headers, content=content)).status_code == 409
    assert (await client.get(path, headers=headers)).json() == []


async def test_concurrent_retries_rollback_and_missing_file(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await make_user()
    target = encode_rid(await support.sense(db, owner.id), "sense")
    content = picture()
    results = await asyncio.gather(
        *[
            images.attach(
                db, test_settings, target, owner.id, "concurrent-request-1", content, "image/png"
            )
            for _ in range(3)
        ]
    )
    assert len({result.id for result in results}) == 1
    assert len(list(test_settings.media_dir.rglob("*.png"))) == 1
    _, _, path = await media.delivery(db, test_settings, results[0].id, owner.id)
    path.unlink()
    from app.core.errors import AppError

    with pytest.raises(AppError, match="missing"):
        await images.attach(
            db, test_settings, target, owner.id, "concurrent-request-1", content, "image/png"
        )
    await images.remove(db, test_settings, target, owner.id, results[0].id)

    async def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("persistence failure")

    monkeypatch.setattr(images.repository, "finish", fail)
    with pytest.raises(RuntimeError, match="persistence"):
        await images.attach(
            db, test_settings, target, owner.id, "rollback-request-01", content, "image/png"
        )
    assert not list(test_settings.media_dir.rglob("*.png"))
    assert not await images.list_images(db, target, owner.id)


async def test_upload_mime_and_stream_limit(
    client: AsyncClient, db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    owner = await make_user()
    target = encode_rid(await support.sense(db), "sense")
    headers = {
        **bearer(await login(client, owner.username)),
        "request-id": "invalid-request-01",
        "Content-Type": "image/jpeg",
    }
    path = f"/api/images/senses/{target}"
    assert (await client.post(path, content=picture(), headers=headers)).status_code == 422

    async def chunks():
        for _ in range(11):
            yield b"x" * 1024 * 1024

    assert (await client.post(path, content=chunks(), headers=headers)).status_code == 413
    content = picture()
    content += b"\0" * (10 * 1024 * 1024 - len(content))
    headers["Content-Type"] = "image/png"
    assert (await client.post(path, content=content, headers=headers)).status_code == 200
