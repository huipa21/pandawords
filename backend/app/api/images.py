from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.api.dependencies import Db, current_user, get_settings
from app.core.config import Settings
from app.core.errors import AppError
from app.domain.auth import User
from app.domain.images import MAX_BYTES, ImageSelection, PixabaySearch
from app.domain.jobs import JobRead
from app.domain.media import MediaRead
from app.services import images, pixabay

router = APIRouter(prefix="/api/images", tags=["images"])
UserDep = Annotated[User, Depends(current_user)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/senses/{sense_id}", response_model=list[MediaRead])
async def list_images(sense_id: str, db: Db, user: UserDep) -> list[MediaRead]:
    return await images.list_images(db, sense_id, user.id)


@router.post(
    "/senses/{sense_id}",
    response_model=MediaRead,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in ("image/jpeg", "image/png", "image/webp", "image/gif")
            },
        }
    },
)
async def upload(
    sense_id: str,
    request: Request,
    db: Db,
    user: UserDep,
    settings: SettingsDep,
    request_id: Annotated[str, Header(pattern=r"^[a-zA-Z0-9_-]{16,80}$")],
) -> MediaRead:
    # Raw encoded uploads avoid parsing/spooling unbounded multipart input before authorization.
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_BYTES:
            raise AppError("image.size", 413, "Maximum image size is 10 MiB.")
        content.extend(chunk)
    return await images.attach(
        db,
        settings,
        sense_id,
        user.id,
        request_id,
        bytes(content),
        request.headers.get("content-type", "").split(";")[0],
    )


@router.delete("/senses/{sense_id}/{image_id}", status_code=204)
async def remove(
    sense_id: str, image_id: str, db: Db, user: UserDep, settings: SettingsDep
) -> Response:
    await images.remove(db, settings, sense_id, user.id, image_id)
    return Response(status_code=204)


@router.get("/pixabay/search", response_model=PixabaySearch)
async def search(
    db: Db,
    user: UserDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> PixabaySearch:
    return await pixabay.search(db, settings, user.id, q)


@router.post("/senses/{sense_id}/pixabay", response_model=JobRead, status_code=202)
async def select(sense_id: str, body: ImageSelection, db: Db, user: UserDep) -> JobRead:
    return await pixabay.select(db, user.id, sense_id, body)
