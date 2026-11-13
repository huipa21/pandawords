from collections.abc import Mapping
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response


class AppError(Exception):
    def __init__(
        self,
        code: str,
        status: int,
        message: str,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.field = field


def _error_response(
    code: str,
    status: int,
    message: str,
    field: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "field": field},
        headers=headers,
    )


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise TypeError(f"Expected AppError, received {type(exc).__name__}.")

    return _error_response(exc.code, exc.status, exc.message, exc.field)


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


async def unhandled_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    headers = {"X-Request-ID": request_id} if isinstance(request_id, str) else None
    return _error_response(
        "internal.error",
        500,
        "Internal server error.",
        headers=headers,
    )
