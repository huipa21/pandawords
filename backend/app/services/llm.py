"""The sole provider boundary; callers handle LlmUnavailable with a non-LLM fallback."""

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any, Never

import structlog
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel
from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.core.errors import LlmUnavailable, LlmUnavailableReason
from app.db import llm as repository
from app.domain.llm import LlmResult


class _NoProviderPayload(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # The SDK's DEBUG request-options events contain prompts and private input.
        return record.levelno > logging.DEBUG


logging.getLogger("openai._base_client").addFilter(_NoProviderPayload())


def _canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _enabled(key: str) -> bool:
    normalized = key.strip().lower()
    return bool(normalized) and not any(
        marker in normalized
        for marker in (
            "replace",
            "your-api-key",
            "your_api_key",
            "example",
            "placeholder",
            "change-me",
            "changeme",
            "sk-xxx",
        )
    )


def _invalid_constant(_value: str) -> Never:
    raise ValueError("Non-standard JSON number")


def _validate[T: BaseModel](raw: str, model: type[T], validate: Callable[[T], bool] | None) -> T:
    try:
        json.loads(raw, parse_constant=_invalid_constant)
        result = model.model_validate_json(raw, strict=True)
    except ValueError:
        raise LlmUnavailable("invalid_response") from None
    if validate is not None:
        try:
            accepted = validate(result)
        except Exception:
            raise LlmUnavailable("rejected_response") from None
        if not accepted:
            raise LlmUnavailable("rejected_response")
    return result


async def generate_json[T: BaseModel](
    db: AsyncSurrealConnection,
    settings: Settings,
    *,
    user: str,
    response_model: type[T],
    prompt: str,
    prompt_version: str,
    schema_version: str,
    inputs: dict[str, Any] | None = None,
    shared_sources: tuple[RecordID, ...] = (),
    validate: Callable[[T], bool] | None = None,
) -> LlmResult[T]:
    """Prompt/version are trusted code, not user text. Put private text only in inputs.

    Shared mode derives all input from shared dictionary records, never overlays. Validators
    must check exercise-specific constraints before either cached or fresh data is returned.
    """
    owner = repository.owner_record(user)
    if not prompt_version.strip() or not schema_version.strip() or not prompt.strip():
        raise ValueError("Prompt and schema versions must be explicit")
    try:
        if shared_sources:
            if inputs is not None:
                raise LlmUnavailable("invalid_scope")
            try:
                inputs = await repository.shared_inputs(db, shared_sources)
            except ValueError:
                raise LlmUnavailable("invalid_scope") from None
            owner = None
        key = hashlib.sha256(
            _canonical(
                {
                    "inputs": inputs or {},
                    "model": settings.deepseek_model,
                    "base_url": settings.deepseek_base_url.rstrip("/"),
                    "prompt": prompt,
                    "prompt_version": prompt_version,
                    "schema_version": schema_version,
                    "schema": response_model.model_json_schema(),
                }
            ).encode()
        ).hexdigest()
        cached = await repository.read_cache(db, key, owner)
    except LlmUnavailable:
        raise
    except Exception:
        raise LlmUnavailable("storage_error") from None
    if cached is not None:
        return LlmResult(value=_validate(cached, response_model, validate), cached=True)
    if not _enabled(settings.deepseek_api_key):
        raise LlmUnavailable("disabled")
    if settings.llm_daily_budget == 0:
        raise LlmUnavailable("budget_exhausted")

    # Disable SDK retries: every dispatch, including our retries, needs a DB reservation.
    try:
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key.strip(),
            base_url=settings.deepseek_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
    except Exception:
        raise LlmUnavailable("provider_error") from None
    async with client:
        for attempt in range(settings.llm_max_retries + 1):
            reason: LlmUnavailableReason
            try:
                reserved = await repository.reserve_attempt(db, user, settings.llm_daily_budget)
            except Exception:
                raise LlmUnavailable("storage_error") from None
            if not reserved:
                raise LlmUnavailable("budget_exhausted")
            try:
                async with asyncio.timeout(settings.llm_timeout_seconds):
                    response = await client.chat.completions.create(
                        model=settings.deepseek_model,
                        messages=[
                            {
                                "role": "system",
                                "content": prompt
                                + "\nReturn JSON matching: "
                                + _canonical(response_model.model_json_schema()),
                            },
                            {"role": "user", "content": _canonical(inputs or {})},
                        ],
                        response_format={"type": "json_object"},
                        max_tokens=2048,
                    )
            except TimeoutError, APITimeoutError:
                reason = "timeout"
                retryable = True
            except (APIConnectionError, APIStatusError) as exc:
                reason = "provider_error"
                retryable = (
                    not isinstance(exc, APIStatusError)
                    or exc.status_code in {408, 409, 429}
                    or exc.status_code >= 500
                )
            except Exception:
                raise LlmUnavailable("provider_error") from None
            else:
                try:
                    if not response.choices or response.choices[0].finish_reason != "stop":
                        raise LlmUnavailable("invalid_response")
                    raw = response.choices[0].message.content
                    if not isinstance(raw, str) or not raw:
                        raise LlmUnavailable("invalid_response")
                except AttributeError, IndexError, TypeError:
                    raise LlmUnavailable("invalid_response") from None
                result = _validate(raw, response_model, validate)
                try:
                    await repository.write_cache(db, key, owner, result.model_dump_json())
                except Exception:
                    raise LlmUnavailable("storage_error") from None
                return LlmResult(value=result, cached=False)
            structlog.get_logger().info(
                "llm_attempt_unavailable", reason=reason, attempt=attempt + 1
            )
            if not retryable or attempt == settings.llm_max_retries:
                raise LlmUnavailable(reason)
            await asyncio.sleep(0.1 * (attempt + 1))
    raise LlmUnavailable("provider_error")
