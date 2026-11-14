"""Real SDK with an in-process transport: no provider network traffic in LLM tests."""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.domain.identity import user_subject
from app.services import llm


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


@pytest.fixture
def settings() -> Settings:
    overrides: dict[str, Any] = {
        "_env_file": None,
        "deepseek_api_key": "sk-test-secret",
        "llm_max_retries": 0,
        "llm_timeout_seconds": 5,
    }
    return Settings(**overrides)


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    state: dict[str, Any] = {"calls": 0, "content": '{"text":"valid"}', "status": 200}

    async def respond(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        state["request"] = request
        if state.get("sleep"):
            await asyncio.sleep(0.2)
        if state.get("error"):
            raise httpx.ConnectError("sk-test-secret private-note", request=request)
        return httpx.Response(
            state["status"],
            json={
                "id": "mock",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-chat",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": state.get("finish", "stop"),
                        "message": {"role": "assistant", "content": state["content"]},
                    },
                ],
            },
        )

    def factory(**kwargs: Any) -> AsyncOpenAI:
        return AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        )

    monkeypatch.setattr(llm, "AsyncOpenAI", factory)
    yield state


async def generate(
    db: AsyncSurrealConnection,
    settings: Settings,
    *,
    user: str | None = None,
    **kwargs: Any,
) -> Any:
    options: dict[str, Any] = {
        "user": user or user_subject("llm_" + uuid4().hex),
        "response_model": Answer,
        "prompt": "Generate a JSON exercise.",
        "prompt_version": "scenario-v1",
        "schema_version": "v1",
        "inputs": {"note": "private-note"},
    }
    options.update(kwargs)
    return await llm.generate_json(db, settings, **options)
