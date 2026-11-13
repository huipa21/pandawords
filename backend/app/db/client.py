from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import cast

import structlog
from fastapi import Request
from surrealdb import AsyncSurreal, AsyncSurrealConnection, ReconnectOptions

from app.core.config import Settings
from app.core.errors import AppError


def database_unavailable() -> AppError:
    return AppError("database.unavailable", 503, "Database is unavailable.")


class DatabaseClient:
    """Own the process connection; the SDK restores its session after a disconnect."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.reconnect = ReconnectOptions(attempts=-1)
        self.connection = AsyncSurreal(
            settings.surreal_url,
            timeout=settings.surreal_timeout_seconds,
            reconnect=self.reconnect,
        )
        self.connected = asyncio.Event()

    async def connect(self) -> None:
        attempt = 0
        while True:
            try:
                async with asyncio.timeout(self.settings.surreal_timeout_seconds):
                    await self.connection.connect()
                    await self.connection.signin(
                        {
                            "username": self.settings.surreal_user,
                            "password": self.settings.surreal_pass,
                        }
                    )
                    await self.connection.use(
                        self.settings.surreal_namespace, self.settings.surreal_database
                    )
                self.connected.set()
                structlog.get_logger().info("database_connected")
                return
            except Exception as exc:
                await self.close()
                attempt += 1
                delay = self.reconnect.delay(attempt)
                structlog.get_logger().warning(
                    "database_connect_failed", error_type=type(exc).__name__, retry_in=delay
                )
                await asyncio.sleep(delay)

    async def close(self) -> None:
        try:
            async with asyncio.timeout(self.settings.surreal_timeout_seconds):
                await self.connection.close()
        except Exception as exc:
            structlog.get_logger().warning("database_close_failed", error_type=type(exc).__name__)

    async def get_connection(self) -> AsyncSurrealConnection:
        try:
            async with asyncio.timeout(self.settings.surreal_timeout_seconds):
                await self.connected.wait()
        except TimeoutError:
            raise database_unavailable() from None
        return self.connection


@asynccontextmanager
async def database_lifespan(settings: Settings) -> AsyncIterator[DatabaseClient]:
    database = DatabaseClient(settings)
    task = asyncio.create_task(database.connect(), name="database_connect")
    try:
        yield database
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await database.close()
        structlog.get_logger().info("database_closed")


async def get_db(request: Request) -> AsyncSurrealConnection:
    database = cast(DatabaseClient, request.app.state.database)
    return await database.get_connection()


async def check_database(db: AsyncSurrealConnection, deadline_seconds: float) -> None:
    try:
        async with asyncio.timeout(deadline_seconds):
            result = await db.query("RETURN 1;")
        if result != [1]:
            raise ValueError("Unexpected readiness result")
    except Exception as exc:
        structlog.get_logger().warning("database_readiness_failed", error_type=type(exc).__name__)
        raise database_unavailable() from None
