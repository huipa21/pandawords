from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp

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
            yield

    app = _GuardedFastAPI(
        title="PandaWords API",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
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
    return app


app = create_app()
