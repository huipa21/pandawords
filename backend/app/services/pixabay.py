import asyncio
import json
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.errors import AppError
from app.db import images as repository
from app.domain.images import MAX_BYTES, ImageSelection, PixabayResult, PixabaySearch
from app.domain.jobs import JobRead, JobRejected
from app.services import images, media

HOSTS = frozenset({"pixabay.com", "cdn.pixabay.com"})
LICENSE = "Pixabay Content License — https://pixabay.com/service/license-summary/"


def approved(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOSTS
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
        or "\\" in url
    ):
        raise AppError("image.provider_url", 422, "Unapproved provider URL.")
    return url


async def fetch(
    url: str, *, params: dict[str, str] | None = None, limit: int = MAX_BYTES
) -> tuple[bytes, str]:
    try:
        async with asyncio.timeout(30):
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                for _ in range(4):
                    async with client.stream("GET", approved(url), params=params) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            url = approved(urljoin(url, response.headers.get("location", "")))
                            params = None
                            continue
                        if response.status_code == 429:
                            raise AppError("image.rate_limit", 429, "Pixabay rate limit reached.")
                        response.raise_for_status()
                        length = response.headers.get("content-length")
                        if length and int(length) > limit:
                            raise AppError("image.size", 422, "Provider response is too large.")
                        content = bytearray()
                        async for chunk in response.aiter_bytes(64 * 1024):
                            if len(content) + len(chunk) > limit:
                                raise AppError("image.size", 422, "Provider response is too large.")
                            content.extend(chunk)
                        return bytes(content), response.headers.get("content-type", "").split(";")[
                            0
                        ]
                raise AppError("image.provider_redirect", 422, "Too many provider redirects.")
    except httpx.HTTPError, TimeoutError, ValueError:
        raise AppError(
            "image.provider_failed", 503, "Pixabay is temporarily unavailable."
        ) from None


def public(identity: str, data: dict[str, Any]) -> PixabaySearch:
    return PixabaySearch(
        search_id=identity,
        results=[
            PixabayResult(
                id=hit["id"],
                creator=hit["creator"],
                source_page=hit["source_page"],
                attribution=hit["attribution"],
            )
            for hit in data["hits"]
        ],
    )


async def search(
    db: AsyncSurrealConnection, settings: Settings, owner: str, query: str
) -> PixabaySearch:
    query = " ".join(query.split())
    if not query or len(query) > 100:
        raise AppError("image.query", 422, "Search query must contain 1–100 characters.")
    identity = repository.key(owner, query)
    cached = await repository.cached(db, owner, identity)
    if cached is not None:
        return public(identity, cached)
    if not settings.pixabay_api_key or settings.pixabay_api_key == "replace-with-your-api-key":
        raise AppError("image.disabled", 503, "Pixabay search is not configured.")
    await repository.rate_limit(db, owner)
    await repository.provider_slot(db)
    try:
        raw, _ = await fetch(
            "https://pixabay.com/api/",
            params={
                "key": settings.pixabay_api_key,
                "q": query,
                "image_type": "photo",
                "safesearch": "true",
                "per_page": "20",
            },
            limit=1024 * 1024,
        )
        response = json.loads(raw)
        hits = []
        for hit in response["hits"][:20]:
            url = approved(hit["webformatURL"])
            page = approved(hit["pageURL"])
            creator = str(hit.get("user", ""))[:200]
            hits.append(
                {
                    "id": int(hit["id"]),
                    "url": url,
                    "source_page": page,
                    "creator": creator,
                    "attribution": f"{creator} · {page} · {LICENSE}",
                }
            )
    except AppError as exc:
        if exc.status == 429:
            await repository.cooldown(db, owner, 3600)
            await repository.provider_slot(db, cooldown=True)
        raise
    except KeyError, TypeError, ValueError:
        raise AppError("image.provider_failed", 503, "Invalid Pixabay response.") from None
    data = {"hits": hits}
    await repository.cache(db, owner, identity, data)
    return public(identity, data)


async def select(
    db: AsyncSurrealConnection, owner: str, target: str, selection: ImageSelection
) -> JobRead:
    await repository.visible(db, images.sense_id(target), owner)
    cached = await repository.cached(db, owner, selection.search_id)
    if cached is None or not any(hit["id"] == selection.result_id for hit in cached["hits"]):
        raise AppError("image.result_expired", 422, "Search result expired. Search again.")
    payload = {"target": target, **selection.model_dump()}
    job = await repository.enqueue_download(db, owner, payload)
    return JobRead.model_validate(job.model_dump(exclude={"owner", "payload"}))


async def download(
    db: AsyncSurrealConnection, settings: Settings, owner: str, payload: dict[str, Any]
) -> None:
    selection = ImageSelection.model_validate(
        {k: payload[k] for k in ("request_id", "search_id", "result_id")}
    )
    try:
        await repository.visible(db, images.sense_id(payload["target"]), owner)
        source_identity = f"{selection.search_id}:{selection.result_id}"
        previous = await repository.prior_download(
            db, owner, selection.request_id, images.sense_id(payload["target"]), source_identity
        )
        if previous is not None:
            if not await media.content_exists(settings, previous):
                raise JobRejected("image.missing_file")
            return
        cached = await repository.cached(db, owner, selection.search_id)
        hit = (
            next((h for h in cached["hits"] if h["id"] == selection.result_id), None)
            if cached
            else None
        )
        if hit is None:
            raise JobRejected("image.result_expired")
        await repository.provider_slot(db)
        try:
            content, mime = await fetch(hit["url"])
        except AppError as exc:
            if exc.status == 429:
                await repository.provider_slot(db, cooldown=True)
            raise
        await images.attach(
            db,
            settings,
            payload["target"],
            owner,
            selection.request_id,
            content,
            mime,
            attribution=hit["attribution"],
            provider_identity=source_identity,
        )
    except AppError as exc:
        if exc.status < 500:
            raise JobRejected(exc.code) from None
        raise
