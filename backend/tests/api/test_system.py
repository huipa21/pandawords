import json
from http import HTTPStatus

import pytest
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic_settings import SettingsConfigDict

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app


class _TestSettings(Settings):
    model_config = SettingsConfigDict(env_file=None)


def test_healthz_and_request_id() -> None:
    with TestClient(create_app(_TestSettings())) as client:
        response = client.get("/api/healthz")
        ready_response = client.get("/api/readyz")
        openapi_response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]
    assert ready_response.status_code == 200
    assert ready_response.json() == {"status": "ok"}
    assert openapi_response.status_code == 200
    assert "/api/healthz" in openapi_response.json()["paths"]


def test_app_error_response_shape() -> None:
    app = create_app(_TestSettings())

    @app.get("/api/test-error")
    async def raise_app_error() -> None:
        raise AppError("word.not_found", 404, "Word not found.", "word_id")

    with TestClient(app) as client:
        response = client.get("/api/test-error")

    assert response.status_code == 404
    assert response.json() == {
        "code": "word.not_found",
        "message": "Word not found.",
        "field": "word_id",
    }
    assert response.headers["x-request-id"]


def test_validation_error_uses_standard_shape() -> None:
    app: FastAPI = create_app(_TestSettings())

    @app.get("/api/test-validation")
    async def validation_endpoint(count: int) -> dict[str, int]:
        return {"count": count}

    with TestClient(app) as client:
        response = client.get("/api/test-validation?count=invalid")

    assert response.status_code == 422
    assert response.json() == {
        "code": "validation.invalid",
        "message": "Request validation failed.",
        "field": "count",
    }
    assert response.headers["x-request-id"]


@pytest.mark.parametrize(
    ("url", "payload", "field"),
    [
        ("/api/test-query?path=invalid", None, "path"),
        ("/api/test-body", {"path": {"body": "invalid"}}, "path.body"),
    ],
)
def test_validation_error_preserves_field_names(
    url: str, payload: dict[str, dict[str, str]] | None, field: str
) -> None:
    app = create_app(_TestSettings())

    @app.get("/api/test-query")
    async def query_endpoint(path: int) -> dict[str, int]:
        return {"path": path}

    @app.post("/api/test-body")
    async def body_endpoint(body: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
        return body

    with TestClient(app) as client:
        response = client.get(url) if payload is None else client.post(url, json=payload)

    assert response.status_code == 422
    assert response.json()["field"] == field


def test_invalid_json_does_not_report_byte_offset_as_field() -> None:
    app = create_app(_TestSettings())

    @app.post("/api/test-json")
    async def json_endpoint(body: dict[str, str]) -> dict[str, str]:
        return body

    with TestClient(app) as client:
        response = client.post(
            "/api/test-json",
            content="{",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "validation.invalid"
    assert response.json()["field"] is None


@pytest.mark.parametrize(
    ("method", "url", "status"),
    [
        ("GET", "/api/does-not-exist", HTTPStatus.NOT_FOUND),
        ("POST", "/api/healthz", HTTPStatus.METHOD_NOT_ALLOWED),
    ],
)
def test_framework_http_errors_use_standard_shape(
    method: str, url: str, status: HTTPStatus
) -> None:
    with TestClient(create_app(_TestSettings())) as client:
        response = client.request(method, url)

    assert response.status_code == status
    assert response.json() == {
        "code": f"http.{status.name.lower()}",
        "message": status.phrase,
        "field": None,
    }
    assert response.headers["x-request-id"]
    if status == HTTPStatus.METHOD_NOT_ALLOWED:
        assert response.headers["allow"] == "GET"


def test_framework_http_error_preserves_headers() -> None:
    app = create_app(_TestSettings())

    @app.get("/api/test-auth")
    async def auth_endpoint() -> None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with TestClient(app) as client:
        response = client.get("/api/test-auth")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "code": "http.unauthorized",
        "message": "Authentication required.",
        "field": None,
    }


def test_http_exception_without_body_preserves_status_and_headers() -> None:
    app = create_app(_TestSettings())

    @app.get("/api/test-not-modified")
    async def not_modified_endpoint() -> None:
        raise HTTPException(status_code=304, headers={"ETag": '"test"'})

    with TestClient(app) as client:
        response = client.get("/api/test-not-modified")

    assert response.status_code == 304
    assert not response.content
    assert response.headers["etag"] == '"test"'
    assert response.headers["x-request-id"]


def test_unknown_http_status_uses_generic_code_and_message() -> None:
    app = create_app(_TestSettings())

    @app.get("/api/test-unknown-status")
    async def unknown_status_endpoint() -> None:
        raise HTTPException(status_code=499, detail={"reason": "not a string"})

    with TestClient(app) as client:
        response = client.get("/api/test-unknown-status")

    assert response.status_code == 499
    assert response.json() == {
        "code": "http.error",
        "message": "HTTP error.",
        "field": None,
    }


def test_unexpected_error_is_safe_and_keeps_logged_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_TestSettings(app_env="production"))

    @app.get("/api/test-failure")
    async def failure_endpoint() -> None:
        structlog.get_logger().info("controlled_failure")
        raise RuntimeError("private error details")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/test-failure?token=example-query-value",
            headers={"Authorization": "Bearer example-header-value"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal.error",
        "message": "Internal server error.",
        "field": None,
    }
    log_output = capsys.readouterr().out
    events = {entry["event"]: entry for entry in map(json.loads, log_output.splitlines())}
    assert {"controlled_failure", "unhandled_error"} <= events.keys()
    request_id = response.headers["x-request-id"]
    assert events["controlled_failure"]["request_id"] == request_id
    assert events["unhandled_error"]["request_id"] == request_id
    assert events["unhandled_error"]["level"] == "error"
    assert events["unhandled_error"]["exception_type"] == "RuntimeError"
    for private_value in ("private error details", "example-query-value", "example-header-value"):
        assert private_value not in log_output
        assert private_value not in response.text
