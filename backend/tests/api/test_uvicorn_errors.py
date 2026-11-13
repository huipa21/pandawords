import asyncio
import json
import logging
import socket

import httpx
import pytest
import uvicorn
from pydantic_settings import SettingsConfigDict
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import HandledErrorGuard, unhandled_error_handler
from app.main import create_app


class _TestSettings(Settings):
    model_config = SettingsConfigDict(env_file=None)


@pytest.mark.anyio
async def test_request_cancellation_propagates() -> None:
    app = create_app(_TestSettings())

    @app.get("/api/test-cancel")
    async def cancelled_endpoint() -> None:
        raise asyncio.CancelledError()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        with pytest.raises(asyncio.CancelledError):
            await client.get("/api/test-cancel")


@pytest.mark.anyio
@pytest.mark.parametrize("fail_during_send", [True, False])
async def test_guard_propagates_unrelated_failures(fail_during_send: bool) -> None:
    scope: Scope = {"type": "http", "state": {"request_id": "test-request"}}
    handled = RuntimeError("handled")

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        if fail_during_send and message["type"] == "http.response.body":
            raise OSError("unrelated_failure")

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        response = await unhandled_error_handler(Request(scope), handled)
        await response(scope, receive, send)
        raise OSError("unrelated_failure")

    with pytest.raises(OSError, match="unrelated_failure"):
        await HandledErrorGuard(app)(scope, receive, send)


@pytest.mark.anyio
async def test_uvicorn_logs_handled_errors_safely_and_propagates_background_failures(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.ERROR, logger="uvicorn.error")
    app = create_app(_TestSettings(app_env="production"))

    @app.get("/api/test-failure")
    async def failure_endpoint() -> None:
        raise RuntimeError("synthetic_private_sentinel")

    @app.get("/api/test-background-failure")
    async def background_failure_endpoint() -> Response:
        async def fail_after_response() -> None:
            raise RuntimeError("synthetic_background_failure")

        return Response("ok", background=BackgroundTask(fail_after_response))

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_config=None, access_log=False, timeout_graceful_shutdown=2)
    )
    server_task = asyncio.create_task(server.serve(sockets=[listener]))

    async def wait_for_start() -> None:
        while not server.started:
            if server_task.done():
                await server_task
                raise AssertionError("Uvicorn exited before starting")
            await asyncio.sleep(0.01)

    async def wait_for_idle() -> None:
        await asyncio.gather(*server.server_state.tasks)

    def uvicorn_errors() -> list[logging.LogRecord]:
        return [
            record
            for record in caplog.records
            if record.name == "uvicorn.error" and record.levelno >= logging.ERROR
        ]

    try:
        await asyncio.wait_for(wait_for_start(), timeout=5)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=3
        ) as client:
            response = await client.get("/api/test-failure")
            await asyncio.wait_for(wait_for_idle(), timeout=5)

            assert response.status_code == 500
            assert response.json() == {
                "code": "internal.error",
                "message": "Internal server error.",
                "field": None,
            }
            captured = capsys.readouterr()
            events = [
                json.loads(line) for line in captured.out.splitlines() if line.startswith("{")
            ]
            error_events = [event for event in events if event["event"] == "unhandled_error"]
            assert len(error_events) == 1
            assert error_events[0]["request_id"] == response.headers["x-request-id"]
            assert error_events[0]["exception_type"] == "RuntimeError"
            assert "synthetic_private_sentinel" not in captured.out + captured.err + caplog.text
            assert not uvicorn_errors()

            assert (await client.get("/api/healthz")).json() == {"status": "ok"}
            background_response = await client.get("/api/test-background-failure")
            await asyncio.wait_for(wait_for_idle(), timeout=5)
            assert background_response.status_code == 200
            assert background_response.text == "ok"
            errors = uvicorn_errors()
            assert len(errors) == 1
            assert "synthetic_background_failure" in logging.Formatter().format(errors[0])
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=5)
        finally:
            listener.close()
