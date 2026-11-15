import json
import logging

import httpx
import pytest
import structlog
from starlette.types import Message, Receive, Scope, Send

from app.core.logging import RequestIdMiddleware, configure_logging


def test_logging_renderer_matches_environment(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("production")
    structlog.get_logger().info("production_event")
    production_output = capsys.readouterr().out
    assert json.loads(production_output)["event"] == "production_event"

    configure_logging("development")
    structlog.get_logger().info("development_event")
    development_output = capsys.readouterr().out
    assert "development_event" in development_output
    assert not development_output.lstrip().startswith("{")


@pytest.mark.anyio
async def test_provider_http_logs_do_not_expose_queries_or_credentials(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.DEBUG)
    for name in ("httpx", "httpcore", "openai"):
        monkeypatch.setattr(logging.getLogger(name), "level", logging.NOTSET)
    configure_logging("production")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    ) as client:
        await client.get(
            "https://pixabay.com/api/",
            params={"key": "synthetic-provider-secret", "q": "synthetic-private-query"},
        )
    logging.getLogger("httpcore.http11").debug("synthetic-authorization-header")
    logging.getLogger("openai._base_client").warning("synthetic-private-prompt")
    for secret in (
        "synthetic-provider-secret",
        "synthetic-private-query",
        "synthetic-authorization-header",
        "synthetic-private-prompt",
    ):
        assert secret not in caplog.text


@pytest.mark.anyio
async def test_request_id_is_added_to_headerless_asgi_response() -> None:
    scope: Scope = {"type": "http"}
    messages: list[Message] = []

    async def app(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204})
        await send({"type": "http.response.body", "body": b""})

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await RequestIdMiddleware(app)(scope, receive, send)

    headers = dict(messages[0]["headers"])
    assert headers[b"x-request-id"].decode() == scope["state"]["request_id"]
