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
)
from app.services import exercise_attempts

router = APIRouter(prefix="/api/exercise-attempts", tags=["exercises"])
Actor = Annotated[User, Depends(current_user)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("", status_code=201)
async def create(data: AttemptCreate, db: Db, actor: Actor, response: Response) -> AttemptRead:
    response.headers["Cache-Control"] = "no-store"
    return await exercise_attempts.create_attempt(db, actor.id, data)


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
        db, config, actor.id, attempt_id, data.answer, data.duration_ms
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
    return await exercise_attempts.submit(db, config, actor.id, attempt_id, None, data.duration_ms)


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
