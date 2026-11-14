from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import APIRouter, Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp

from app.api.add_to_project import router as add_to_project_router
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.candidates import router as candidates_router
from app.api.jobs import router as jobs_router
from app.api.media import router as media_router
from app.api.notes import router as notes_router
from app.api.overrides import router as overrides_router
from app.api.projects import router as projects_router
from app.api.user_dictionary import router as user_dictionary_router
from app.core.config import Settings
from app.core.errors import (
    AppError,
    HandledErrorGuard,
    app_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import RequestIdMiddleware, configure_logging
from app.db.client import database_lifespan
from app.services.auth import bootstrap_admin
from app.services.login_backoff import LoginBackoff
from app.services.system import check_readiness


class _GuardedFastAPI(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        return HandledErrorGuard(super().build_middleware_stack())


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure_logging(app_settings.app_env)
        async with database_lifespan(app_settings) as database:
            _app.state.database = database

            async def initialize_auth() -> None:
                await database.connected.wait()
                await bootstrap_admin(database.connection, app_settings)

            def report_failure(task: asyncio.Task[None]) -> None:
                if not task.cancelled() and (error := task.exception()) is not None:
                    structlog.get_logger().error(
                        "auth_bootstrap_failed", error_type=type(error).__name__
                    )

            task = asyncio.create_task(initialize_auth(), name="auth_bootstrap")
            task.add_done_callback(report_failure)
            _app.state.auth_initialization = task
            try:
                done, _ = await asyncio.wait([task], timeout=app_settings.surreal_timeout_seconds)
                if done:
                    await task
                # DB outages preserve health/OpenAPI, but not authentication readiness.
                yield
            finally:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

    app = _GuardedFastAPI(
        title="PandaWords API",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.login_backoff = LoginBackoff()
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    router = APIRouter(prefix="/api")

    @router.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/readyz", tags=["system"], dependencies=[Depends(check_readiness)])
    async def readyz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(media_router)
    app.include_router(admin_router)
    app.include_router(projects_router)
    app.include_router(candidates_router)
    app.include_router(add_to_project_router)
    app.include_router(user_dictionary_router)
    app.include_router(overrides_router)
    app.include_router(notes_router)
    return app


app = create_app()
