from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise TypeError(f"Expected AppError, received {type(exc).__name__}.")

    return JSONResponse(
        status_code=exc.status,
        content={"code": exc.code, "message": exc.message, "field": exc.field},
    )


async def validation_error_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise TypeError(f"Expected RequestValidationError, received {type(exc).__name__}.")

    errors = exc.errors()
    field: str | None = None
    for error in errors:
        field_parts = [
            str(part)
            for part in error["loc"]
            if part not in {"body", "query", "path", "header", "cookie"}
        ]
        if field_parts:
            field = ".".join(field_parts)
            break

    return JSONResponse(
        status_code=422,
        content={
            "code": "validation.invalid",
            "message": "Request validation failed.",
            "field": field,
        },
    )
