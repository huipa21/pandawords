import math
from collections.abc import Mapping
from http import HTTPStatus
from typing import Literal

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HANDLED_ERROR_KEY = "pandawords.handled_error"


def retry_headers(seconds: float) -> dict[str, str]:
    return {"Retry-After": str(max(1, math.ceil(seconds))), "Cache-Control": "no-store"}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        status: int,
        message: str,
        field: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.field = field
        self.headers = headers


type LlmUnavailableReason = Literal[
    "disabled",
    "budget_exhausted",
    "timeout",
    "provider_error",
    "invalid_response",
    "rejected_response",
    "storage_error",
    "invalid_scope",
]


class LlmUnavailable(AppError):
    def __init__(self, reason: LlmUnavailableReason) -> None:
        self.reason = reason
        super().__init__("llm." + reason, 503, "Optional LLM is unavailable.")


type BundleStage = Literal["upload", "archive", "manifest", "data", "references", "media", "apply"]


class BundleError(AppError):
    """Rejected bundle; ``problems`` are short, path-free and safe to show to the uploader."""

    def __init__(
        self,
        reason: str,
        stage: BundleStage,
        problems: list[str] | None = None,
        status: int = 422,
    ) -> None:
        self.reason = reason
        self.stage = stage
        self.problems = problems or []
        super().__init__("bundle." + reason, status, f"Bundle rejected at {stage} stage.")


def _error_response(
    code: str,
    status: int,
    message: str,
    field: str | None = None,
    headers: Mapping[str, str] | None = None,
    extra: Mapping[str, object] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "field": field, **(extra or {})},
        headers=headers,
    )


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise TypeError(f"Expected AppError, received {type(exc).__name__}.")

    extra = {"stage": exc.stage, "problems": exc.problems} if isinstance(exc, BundleError) else None
    return _error_response(exc.code, exc.status, exc.message, exc.field, exc.headers, extra)


async def validation_error_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise TypeError(f"Expected RequestValidationError, received {type(exc).__name__}.")

    errors = exc.errors()
    field: str | None = None
    for error in errors:
        if error.get("type") == "json_invalid":
            break
        location = error["loc"]
        if location and location[0] in {"body", "query", "path", "header", "cookie"}:
            location = location[1:]
        if location:
            field = ".".join(str(part) for part in location)
            break

    return _error_response("validation.invalid", 422, "Request validation failed.", field=field)


async def http_error_handler(_request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):
        raise TypeError(f"Expected HTTPException, received {type(exc).__name__}.")

    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=exc.headers)

    try:
        status = HTTPStatus(exc.status_code)
    except ValueError:
        code = "http.error"
        default_message = "HTTP error."
    else:
        code = f"http.{status.name.lower()}"
        default_message = status.phrase

    message = exc.detail if isinstance(exc.detail, str) else default_message
    return _error_response(code, exc.status_code, message, headers=exc.headers)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    safe_request_id = request_id if isinstance(request_id, str) else None
    structlog.get_logger().error(
        "unhandled_error",
        request_id=safe_request_id,
        exception_type=type(exc).__name__,
    )
    headers = {"X-Request-ID": safe_request_id} if safe_request_id is not None else None
    response = _error_response(
        "internal.error",
        500,
        "Internal server error.",
        headers=headers,
    )
    request.scope[_HANDLED_ERROR_KEY] = exc
    return response


class HandledErrorGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        sending_error_response = False
        error_response_complete = False

        async def tracked_send(message: Message) -> None:
            nonlocal sending_error_response, error_response_complete
            if message["type"] == "http.response.start":
                sending_error_response = (
                    scope.get(_HANDLED_ERROR_KEY) is not None and message["status"] == 500
                )
            await send(message)
            if (
                sending_error_response
                and message["type"] == "http.response.body"
                and not message.get("more_body", False)
            ):
                error_response_complete = True

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            # Starlette re-raises the handled exception after sending its response.
            if not (error_response_complete and scope.get(_HANDLED_ERROR_KEY) is exc):
                raise
        finally:
            scope.pop(_HANDLED_ERROR_KEY, None)
