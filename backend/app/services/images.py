import asyncio
import hashlib
import re
from pathlib import Path
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import images as repository
from app.db import media as media_repository
from app.db.auth import _atomic, _finish_cleanup
from app.domain.media import MIME_EXTENSIONS, MediaCreate, MediaRead
from app.services import image_validation, media


def sense_id(value: str) -> RecordID:
    try:
        return decode_rid(value, "sense")
    except ValueError:
        raise AppError("image.not_found", 404, "Sense or image not found.") from None


async def list_images(db: AsyncSurrealConnection, target: str, owner: str) -> list[MediaRead]:
    records = await repository.list_images(db, sense_id(target), owner)
    return [media._public(record) for record in records]


async def attach(
    db: AsyncSurrealConnection,
    settings: Settings,
    target: str,
    owner: str,
    identity: str,
    content: bytes,
    mime: str,
    *,
    attribution: str | None = None,
    provider_identity: str | None = None,
) -> MediaRead:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", identity):
        raise AppError("image.request_id", 422, "Invalid request identity.")
    record = sense_id(target)
    await repository.visible(db, record, owner)
    await asyncio.to_thread(image_validation.validate, content, mime)
    fingerprint = hashlib.sha256(
        (provider_identity or "upload").encode() + b"\0" + mime.encode() + b"\0" + content
    ).hexdigest()
    paths: list[Path] = []
    winner: str | None = None

    async def operation(txn: UUID) -> MediaRead:
        nonlocal winner
        previous = await repository.request(
            db, owner, identity, record, fingerprint, txn, provider_identity
        )
        if previous is not None:
            existing = await media_repository.read(db, previous, owner)
            if existing is None or existing.owner != owner or existing.target != record:
                raise AppError("image.not_found", 404, "Image not found.")
            if not await media.content_exists(settings, existing):
                raise AppError(
                    "image.missing_file", 409, "Remove the missing image and upload again."
                )
            winner = existing.path
            return media._public(existing)
        key = uuid4().hex
        path = f"image/{key}{MIME_EXTENSIONS['image'][mime]}"
        paths.append(media._file(settings.media_dir, path))
        result = await media.store(
            db,
            settings,
            MediaCreate(
                target=record,
                owner=owner,
                kind="image",
                mime=mime,
                source="pixabay" if provider_identity else "upload",
                attribution=attribution,
            ),
            content,
            txn_id=txn,
            key=key,
        )
        await repository.finish(db, owner, identity, decode_rid(result.id, "media"), txn)
        winner = path
        return result

    committed = False
    try:
        # Finish the transaction before deciding which files survived a disconnected request.
        result, cancellation = await _finish_cleanup(asyncio.create_task(_atomic(db, operation)))
        committed = True
        if cancellation is not None:
            raise cancellation
        return result
    finally:
        for path in paths:
            if not committed or path != media._file(settings.media_dir, winner or "image/none"):
                await asyncio.to_thread(path.unlink, missing_ok=True)


async def remove(
    db: AsyncSurrealConnection, settings: Settings, target: str, owner: str, image_id: str
) -> None:
    try:
        record = decode_rid(image_id, "media")
    except ValueError:
        raise AppError("image.not_found", 404, "Image not found.") from None
    path = await repository.remove(db, sense_id(target), owner, record)
    if path:
        try:
            await asyncio.to_thread(media._file(settings.media_dir, path).unlink, missing_ok=True)
        except ValueError:
            pass
