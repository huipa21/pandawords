"""Authenticated private reading API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.api.dependencies import Db, current_user, get_lexicon_reader, get_settings
from app.core.config import Settings
from app.domain.auth import User
from app.domain.content import (
    AnalysisRead,
    ContentCreate,
    ContentKind,
    ContentRead,
    PartAssignment,
    PassageRead,
    Resolution,
)
from app.services import content
from app.services.lexicon import LexiconReader

router = APIRouter(prefix="/api/content", tags=["content"])
Actor = Annotated[User, Depends(current_user)]
Lexicon = Annotated[LexiconReader, Depends(get_lexicon_reader)]
Config = Annotated[Settings, Depends(get_settings)]
PartOrder = Annotated[int, Path(ge=0, le=199)]


@router.put("/passage/{id}/sentences/{order}", status_code=204)
async def assign_part(
    id: str, order: PartOrder, data: PartAssignment, db: Db, actor: Actor
) -> Response:
    await content.assign_part(db, actor.id, id, data.sentence_id, order)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.delete("/passage/{id}/sentences/{order}", status_code=204)
async def remove_part(id: str, order: PartOrder, db: Db, actor: Actor) -> Response:
    await content.remove_part(db, actor.id, id, order)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/ingest", status_code=201)
async def ingest(
    data: ContentCreate, db: Db, actor: Actor, reader: Lexicon, response: Response
) -> PassageRead:
    response.headers["Cache-Control"] = "no-store"
    return await content.ingest(db, reader, actor.id, data)


@router.get("/passage/{id}/reading")
async def reading(
    id: str,
    db: Db,
    actor: Actor,
    reader: Lexicon,
    response: Response,
    project_id: str | None = None,
) -> PassageRead:
    response.headers["Cache-Control"] = "no-store"
    return await content.passage(db, reader, actor.id, id, project_id)


@router.get("/sentence/{id}/occurrences")
async def occurrences(
    id: str,
    db: Db,
    actor: Actor,
    reader: Lexicon,
    settings: Config,
    response: Response,
    assist: bool = False,
) -> AnalysisRead:
    response.headers["Cache-Control"] = "no-store"
    return await content.analysis(db, reader, settings, actor.id, id, assist)


@router.put("/sentence/{id}/occurrences")
async def resolve(
    id: str, data: Resolution, db: Db, actor: Actor, reader: Lexicon, response: Response
) -> AnalysisRead:
    response.headers["Cache-Control"] = "no-store"
    return await content.resolve(db, reader, actor.id, id, data)


@router.delete("/sentence/{id}/occurrences/{edge_id}", status_code=204)
async def remove_occurrence(id: str, edge_id: str, db: Db, actor: Actor) -> Response:
    await content.remove_occurrence(db, actor.id, id, edge_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/{kind}", status_code=201)
async def create(
    kind: ContentKind, data: ContentCreate, db: Db, actor: Actor, response: Response
) -> ContentRead:
    response.headers["Cache-Control"] = "no-store"
    return await content.create(db, actor.id, kind, data)


@router.get("/{kind}")
async def listing(
    kind: ContentKind,
    db: Db,
    actor: Actor,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> list[ContentRead]:
    response.headers["Cache-Control"] = "no-store"
    return await content.listing(db, actor.id, kind, limit, offset)


@router.get("/{kind}/{id}")
async def read(kind: ContentKind, id: str, db: Db, actor: Actor, response: Response) -> ContentRead:
    response.headers["Cache-Control"] = "no-store"
    return await content.get(db, actor.id, kind, id)


@router.put("/{kind}/{id}")
async def update(
    kind: ContentKind, id: str, data: ContentCreate, db: Db, actor: Actor, response: Response
) -> ContentRead:
    response.headers["Cache-Control"] = "no-store"
    return await content.update(db, actor.id, kind, id, data)


@router.delete("/{kind}/{id}", status_code=204)
async def delete(kind: ContentKind, id: str, db: Db, actor: Actor) -> Response:
    await content.delete(db, actor.id, kind, id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
