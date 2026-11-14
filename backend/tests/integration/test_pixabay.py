import asyncio
import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db import images as repository
from app.db import media_test_support as support
from app.domain.images import ImageSelection
from app.domain.jobs import JobRejected
from app.services import images, pixabay
from tests.conftest import UserFactory
from tests.unit.test_image_validation import picture

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def image_directory(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    with TemporaryDirectory(dir=Path.cwd(), prefix=".pixabay-") as directory:
        root = Path(directory)
        monkeypatch.setattr(test_settings, "media_dir", root)
        yield root


async def test_cached_search_selection_worker_owner_and_attribution(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, other = await make_user(), await make_user()
    monkeypatch.setattr(test_settings, "pixabay_api_key", "test-secret")
    target = encode_rid(await support.sense(db), "sense")
    private = encode_rid(await support.sense(db, owner.id), "sense")
    calls = []

    async def fetch(url: str, **kwargs: object) -> tuple[bytes, str]:
        calls.append(url)
        if url.endswith("/api/"):
            return json.dumps(
                {
                    "hits": [
                        {
                            "id": 123,
                            "user": "Creator",
                            "pageURL": "https://pixabay.com/photos/123/",
                            "webformatURL": "https://cdn.pixabay.com/photo/123.png",
                        }
                    ]
                }
            ).encode(), "application/json"
        return picture(), "image/png"

    monkeypatch.setattr(pixabay, "fetch", fetch)
    result = await pixabay.search(db, test_settings, owner.id, "  apple  ")
    assert result == await pixabay.search(db, test_settings, owner.id, "apple")
    assert len(calls) == 1
    assert "url" not in result.model_dump()["results"][0]
    assert await repository.cached(db, other.id, result.search_id) is None
    assert (
        await pixabay.search(db, test_settings, other.id, "apple")
    ).search_id != result.search_id
    assert len(calls) == 2
    with pytest.raises(AppError) as limited:
        await pixabay.search(db, test_settings, owner.id, "pear")
    assert limited.value.status == 429
    selection = ImageSelection(
        request_id="pixabay-request-0001", search_id=result.search_id, result_id=123
    )
    with pytest.raises(AppError):
        await pixabay.select(db, other.id, target, selection)
    with pytest.raises(AppError):
        await pixabay.select(db, other.id, private, selection)
    first = await pixabay.select(db, owner.id, target, selection)
    assert first.id == (await pixabay.select(db, owner.id, target, selection)).id
    with pytest.raises(AppError) as conflict:
        await pixabay.select(db, owner.id, private, selection)
    assert conflict.value.status == 409
    payload = {"target": target, **selection.model_dump()}
    await asyncio.gather(
        pixabay.download(db, test_settings, owner.id, payload),
        pixabay.download(db, test_settings, owner.id, payload),
    )
    attached = await images.list_images(db, target, owner.id)
    assert len(attached) == 1
    assert attached[0].source == "pixabay"
    assert "Creator" in (attached[0].attribution or "")
    assert "Pixabay Content License" in (attached[0].attribution or "")
    assert not await images.list_images(db, target, other.id)
    assert len(list(test_settings.media_dir.rglob("*.png"))) == 1
    await support.change(db, RecordID("job", first.id), {"status": "failed", "attempts": 5})
    retried = await pixabay.select(db, owner.id, target, selection)
    assert retried.id == first.id and retried.status == "queued" and retried.attempts == 0
    for index in range(9):
        await pixabay.select(
            db,
            owner.id,
            target,
            selection.model_copy(
                update={
                    "request_id": f"bounded-request-{index:04d}",
                }
            ),
        )
    with pytest.raises(AppError) as full:
        await pixabay.select(
            db,
            owner.id,
            target,
            selection.model_copy(
                update={
                    "request_id": "bounded-request-full",
                }
            ),
        )
    assert full.value.status == 429
    await repository.cache(db, owner.id, result.search_id, {"hits": []})
    payload["request_id"] = "pixabay-expired-0001"
    with pytest.raises(JobRejected, match="expired"):
        await pixabay.download(db, test_settings, owner.id, payload)


async def test_missing_key_empty_and_failed_provider(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await make_user()
    monkeypatch.setattr(test_settings, "pixabay_api_key", "")
    with pytest.raises(AppError, match="not configured"):
        await pixabay.search(db, test_settings, owner.id, "cat")
    monkeypatch.setattr(test_settings, "pixabay_api_key", "test-secret")

    async def empty(*args: object, **kwargs: object) -> tuple[bytes, str]:
        return b'{"hits":[]}', "application/json"

    monkeypatch.setattr(pixabay, "fetch", empty)
    assert not (await pixabay.search(db, test_settings, owner.id, "cat")).results
    assert not (await pixabay.search(db, test_settings, owner.id, "cat")).results


async def test_cache_expires_at_24_hours_and_provider_failures(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await make_user()
    monkeypatch.setattr(test_settings, "pixabay_api_key", "test-secret")
    calls = 0

    async def fetch(*args: object, **kwargs: object) -> tuple[bytes, str]:
        nonlocal calls
        calls += 1
        return b'{"hits":[]}', "application/json"

    monkeypatch.setattr(pixabay, "fetch", fetch)
    await pixabay.search(db, test_settings, owner.id, "clock")

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(hours=25)

    monkeypatch.setattr(repository, "datetime", Later)
    await pixabay.search(db, test_settings, owner.id, "clock")
    assert calls == 2
    another = await make_user()

    async def broken(*args: object, **kwargs: object) -> tuple[bytes, str]:
        raise AppError("image.provider_failed", 503, "Provider failed.")

    monkeypatch.setattr(pixabay, "fetch", broken)
    with pytest.raises(AppError, match="Provider failed"):
        await pixabay.search(db, test_settings, another.id, "failure")
    assert await repository.cached(db, another.id, repository.key(another.id, "failure")) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://cdn.pixabay.com/x",
        "https://evil.example/x",
        "https://pixabay.com.evil.example/x",
        "https://user:password@pixabay.com/x",
        "https://pixabay.com:444/x",
        "https://127.0.0.1/x",
        "file:///etc/passwd",
        "https://pixabay.com\\@evil.example/x",
    ],
)
def test_approved_hosts_only(url: str) -> None:
    with pytest.raises(AppError):
        pixabay.approved(url)


@pytest.mark.parametrize("case", ["redirect", "oversize", "timeout", "rate", "redirect_loop"])
async def test_bounded_provider_http(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    real_client = httpx.AsyncClient
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if case == "redirect":
            return httpx.Response(302, headers={"location": "https://evil.example/image"})
        if case == "oversize":
            return httpx.Response(200, content=b"x" * 11)
        if case == "timeout":
            raise httpx.ReadTimeout("timeout")
        if case == "rate":
            return httpx.Response(429)
        return httpx.Response(302, headers={"location": "https://cdn.pixabay.com/again"})

    def client(**kwargs: object) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(pixabay.httpx, "AsyncClient", client)
    with pytest.raises(AppError):
        await pixabay.fetch("https://cdn.pixabay.com/image", limit=10)
    assert all(url.startswith("https://cdn.pixabay.com/") for url in seen)
