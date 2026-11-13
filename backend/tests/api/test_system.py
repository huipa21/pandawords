from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app


def test_healthz_and_request_id() -> None:
    with TestClient(create_app(Settings())) as client:
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
    app = create_app(Settings())

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


def test_validation_error_uses_standard_shape() -> None:
    app: FastAPI = create_app(Settings())

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
