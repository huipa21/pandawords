import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError, retry_headers
from app.db import jobs as job_repository
from app.db.auth import _atomic, _rows
from app.db.media import _media, _owner
from app.domain.jobs import Job, JobCreate
from app.domain.media import Media


def key(owner: str, identity: str) -> str:
    return hashlib.sha256(json.dumps([owner, identity]).encode()).hexdigest()


async def visible(
    db: AsyncSurrealConnection, target: RecordID, owner: str, txn_id: UUID | None = None
) -> None:
    rows = await _rows(
        db,
        "SELECT id FROM $target WHERE owner = NONE OR owner = $user;",
        {"target": target, "user": _owner(owner)},
        txn_id=txn_id,
    )
    if not rows:
        raise AppError("image.not_found", 404, "Sense or image not found.")


async def list_images(db: AsyncSurrealConnection, target: RecordID, owner: str) -> list[Media]:
    await visible(db, target, owner)
    rows = await _rows(
        db,
        "SELECT * FROM media WHERE target = $target AND owner = $user "
        "AND kind = 'image' ORDER BY id;",
        {"target": target, "user": _owner(owner)},
    )
    return [_media(row) for row in rows]


async def request(
    db: AsyncSurrealConnection,
    owner: str,
    identity: str,
    target: RecordID,
    fingerprint: str,
    txn_id: UUID,
    source_identity: str | None = None,
) -> RecordID | None:
    await visible(db, target, owner, txn_id)
    record = RecordID("image_request", key(owner, identity))
    rows = await _rows(
        db,
        "SELECT * FROM $id WHERE owner = $user;",
        {"id": record, "user": _owner(owner)},
        txn_id=txn_id,
    )
    if rows:
        row = rows[0]
        if row["fingerprint"] != fingerprint or row["target"] != target:
            raise AppError("image.request_conflict", 409, "Request identity already used.")
        if not row.get("media"):
            raise AppError("image.removed", 409, "This attachment was removed.")
        return row["media"]
    await _rows(
        db,
        "CREATE $id CONTENT $data;",
        {
            "id": record,
            "data": {
                "owner": _owner(owner),
                "target": target,
                "fingerprint": fingerprint,
                "source_identity": source_identity,
            },
        },
        txn_id=txn_id,
    )
    return None


async def prior_download(
    db: AsyncSurrealConnection, owner: str, identity: str, target: RecordID, source_identity: str
) -> Media | None:
    await visible(db, target, owner)
    rows = await _rows(
        db,
        "SELECT * FROM $id WHERE owner = $user;",
        {
            "id": RecordID("image_request", key(owner, identity)),
            "user": _owner(owner),
        },
    )
    if not rows:
        return None
    row = rows[0]
    if row["target"] != target or row.get("source_identity") != source_identity:
        raise AppError("image.request_conflict", 409, "Request identity already used.")
    if not row.get("media"):
        raise AppError("image.removed", 409, "This attachment was removed.")
    media = await _rows(
        db,
        "SELECT * FROM $id WHERE owner = $user AND target = $target;",
        {
            "id": row["media"],
            "user": _owner(owner),
            "target": target,
        },
    )
    if not media:
        raise AppError("image.not_found", 404, "Image not found.")
    return _media(media[0])


async def provider_slot(db: AsyncSurrealConnection, *, cooldown: bool = False) -> None:
    async def operation(txn: UUID) -> None:
        record = RecordID("image_provider_rate", "pixabay")
        now = datetime.now(UTC)
        rows = await _rows(db, "SELECT * FROM $id;", {"id": record}, txn_id=txn)
        row = rows[0] if rows else {}
        active = row.get("until", now) > now
        count = row.get("count", 0) if active else 0
        if not cooldown and count >= 80:
            raise AppError(
                "image.rate_limit",
                429,
                "Pixabay rate limit reached.",
                headers=retry_headers((row["until"] - now).total_seconds()),
            )
        await _rows(
            db,
            "UPSERT $id CONTENT $data;",
            {
                "id": record,
                "data": {
                    "until": now + timedelta(hours=1)
                    if cooldown
                    else (row["until"] if active else now + timedelta(minutes=1)),
                    "count": 80 if cooldown else count + 1,
                },
            },
            txn_id=txn,
        )

    await _atomic(db, operation)


async def finish(
    db: AsyncSurrealConnection, owner: str, identity: str, media: RecordID, txn_id: UUID
) -> None:
    await _rows(
        db,
        "UPDATE $id SET media = $media WHERE owner = $user;",
        {
            "id": RecordID("image_request", key(owner, identity)),
            "user": _owner(owner),
            "media": media,
        },
        txn_id=txn_id,
    )


async def remove(db: AsyncSurrealConnection, target: RecordID, owner: str, record: RecordID) -> str:
    async def operation(txn: UUID) -> str:
        await visible(db, target, owner, txn)
        params = {"id": record, "target": target, "user": _owner(owner)}
        rows = await _rows(
            db,
            "SELECT * FROM $id WHERE target = $target AND owner = $user AND kind = 'image';",
            params,
            txn_id=txn,
        )
        if not rows:
            raise AppError("image.not_found", 404, "Sense or image not found.")
        await _rows(db, "DELETE $id WHERE owner = $user RETURN BEFORE;", params, txn_id=txn)
        await _rows(
            db,
            "UPDATE image_request SET media = NONE WHERE owner = $user AND media = $id;",
            params,
            txn_id=txn,
        )
        others = await _rows(
            db,
            "SELECT id FROM media WHERE path = $path LIMIT 1;",
            {"path": rows[0]["path"]},
            txn_id=txn,
        )
        return "" if others else rows[0]["path"]

    return await _atomic(db, operation)


async def cached(db: AsyncSurrealConnection, owner: str, identity: str) -> dict[str, Any] | None:
    rows = await _rows(
        db,
        "SELECT * FROM $id WHERE owner = $user AND expires_at > $now;",
        {"id": RecordID("image_search", identity), "user": _owner(owner), "now": datetime.now(UTC)},
    )
    return json.loads(rows[0]["data"]) if rows else None


async def cache(
    db: AsyncSurrealConnection, owner: str, identity: str, data: dict[str, Any]
) -> None:
    await _rows(
        db,
        "UPSERT $id CONTENT $data;",
        {
            "id": RecordID("image_search", identity),
            "data": {
                "owner": _owner(owner),
                "expires_at": datetime.now(UTC) + timedelta(hours=24),
                "data": json.dumps(data),
            },
        },
    )


async def rate_limit(db: AsyncSurrealConnection, owner: str, seconds: int = 2) -> None:
    async def operation(txn: UUID) -> None:
        record = RecordID("image_rate", key(owner, "rate"))
        now = datetime.now(UTC)
        rows = await _rows(
            db,
            "SELECT * FROM $id WHERE owner = $user;",
            {"id": record, "user": _owner(owner)},
            txn_id=txn,
        )
        if rows and rows[0]["until"] > now:
            raise AppError(
                "image.rate_limit",
                429,
                "Please wait before another provider request.",
                headers=retry_headers((rows[0]["until"] - now).total_seconds()),
            )
        await _rows(
            db,
            "UPSERT $id CONTENT $data;",
            {
                "id": record,
                "data": {
                    "owner": _owner(owner),
                    "until": now + timedelta(seconds=seconds),
                    "revision": 0,
                },
            },
            txn_id=txn,
        )

    await _atomic(db, operation)


async def cooldown(db: AsyncSurrealConnection, owner: str, seconds: int) -> None:
    await _rows(
        db,
        "UPSERT $id CONTENT $data;",
        {
            "id": RecordID("image_rate", key(owner, "rate")),
            "data": {
                "owner": _owner(owner),
                "until": datetime.now(UTC) + timedelta(seconds=seconds),
                "revision": 0,
            },
        },
    )


async def enqueue_download(db: AsyncSurrealConnection, owner: str, payload: dict[str, Any]) -> Job:
    async def operation(txn: UUID) -> Job:
        # A real owner-scoped write serializes submissions across different request IDs.
        await _rows(
            db,
            "UPSERT $id SET owner = $user, until = $now, revision += 1;",
            {
                "id": RecordID("image_rate", key(owner, "queue")),
                "user": _owner(owner),
                "now": datetime.now(UTC),
            },
            txn_id=txn,
        )
        pending = await _rows(
            db,
            "SELECT id FROM job WHERE owner = $user AND type = 'image' "
            "AND status IN ['queued', 'running'] LIMIT 10;",
            {"user": _owner(owner)},
            txn_id=txn,
        )
        job = await job_repository.enqueue(
            db,
            JobCreate(type="image", owner=owner, payload=payload),
            dedup_key=f"image:{payload['request_id']}",
            txn_id=txn,
        )
        if job.payload != payload:
            raise AppError("image.request_conflict", 409, "Request identity already used.")
        if len(pending) >= 10 and job.id not in {str(row["id"].id) for row in pending}:
            raise AppError(
                "image.queue_full",
                429,
                "Too many pending image downloads.",
                headers=retry_headers(5),
            )
        if job.status == "failed":
            await _rows(
                db,
                "UPDATE $id SET status = 'queued', attempts = 0, error = NONE, "
                "run_after = $now WHERE owner = $user;",
                {"id": RecordID("job", job.id), "user": _owner(owner), "now": datetime.now(UTC)},
                txn_id=txn,
            )
            job.status = "queued"
            job.attempts = 0
            job.error = None
        return job

    return await _atomic(db, operation)
