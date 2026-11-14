"""Task-local dependencies for registered Job-only handlers."""

from contextvars import ContextVar
from dataclasses import dataclass

from surrealdb import AsyncSurrealConnection

from app.core.config import Settings


@dataclass(frozen=True)
class HandlerContext:
    db: AsyncSurrealConnection
    settings: Settings


HANDLER_CONTEXT: ContextVar[HandlerContext | None] = ContextVar("worker_context", default=None)


def get_context() -> HandlerContext:
    context = HANDLER_CONTEXT.get()
    if context is None:
        raise RuntimeError("Worker handler must run through worker dispatch.")
    return context
