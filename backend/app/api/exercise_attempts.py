from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import Db, current_user, get_settings
from app.core.config import Settings
from app.domain.auth import User
from app.domain.exercises import (
    AttemptAnswer,
    AttemptConfirm,
    AttemptCreate,
    AttemptGiveUp,
    AttemptRead,
    OfflineBatchRead,
    OfflinePrefetch,
)
from app.services import exercise_attempts, offline_review
from app.services.exercise_recall import build_registry

router = APIRouter(prefix="/api/exercise-attempts", tags=["exercises"])
Actor = Annotated[User, Depends(current_user)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("/offline")
async def prefetch_offline(
    data: OfflinePrefetch, db: Db, config: Config, actor: Actor, response: Response
) -> OfflineBatchRead:
    response.headers["Cache-Control"] = "no-store"
    return await offline_review.prefetch(
        db, actor.id, data, plugins=build_registry(db, config, actor.prefs.accent)
    )


@router.post("", status_code=201)
async def create(
    data: AttemptCreate, db: Db, config: Config, actor: Actor, response: Response
) -> AttemptRead:
    response.headers["Cache-Control"] = "no-store"
    return await exercise_attempts.create_attempt(
        db, actor.id, data, plugins=build_registry(db, config, actor.prefs.accent)
    )


@router.get("/{attempt_id}")
async def read(attempt_id: str, db: Db, actor: Actor, response: Response) -> AttemptRead:
    response.headers["Cache-Control"] = "no-store"
    return await exercise_attempts.read_attempt(db, actor.id, attempt_id)


@router.post("/{attempt_id}/hint")
async def hint(attempt_id: str, db: Db, actor: Actor, response: Response) -> AttemptRead:
    response.headers["Cache-Control"] = "no-store"
    return await exercise_attempts.request_hint(db, actor.id, attempt_id)


@router.post("/{attempt_id}/answer")
async def answer(
    attempt_id: str,
    data: AttemptAnswer,
    db: Db,
    config: Config,
    actor: Actor,
    response: Response,
) -> AttemptRead:
    response.headers["Cache-Control"] = "no-store"
    return await exercise_attempts.submit(
        db,
        config,
        actor.id,
        attempt_id,
        data.answer,
        data.duration_ms,
        plugins=build_registry(db, config, actor.prefs.accent),
        client_key=data.client_key,
    )


@router.post("/{attempt_id}/giveup")
async def give_up(
    attempt_id: str,
    data: AttemptGiveUp,
    db: Db,
    config: Config,
    actor: Actor,
    response: Response,
) -> AttemptRead:
    response.headers["Cache-Control"] = "no-store"
    return await exercise_attempts.submit(
        db,
        config,
        actor.id,
        attempt_id,
        None,
        data.duration_ms,
        plugins=build_registry(db, config, actor.prefs.accent),
        client_key=data.client_key,
    )


@router.post("/{attempt_id}/confirm")
async def confirm(
    attempt_id: str,
    data: AttemptConfirm,
    db: Db,
    actor: Actor,
    response: Response,
) -> AttemptRead:
    response.headers["Cache-Control"] = "no-store"
    return await exercise_attempts.confirm(db, actor.id, attempt_id, data.rating)
