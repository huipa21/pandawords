import asyncio
from contextlib import suppress

import structlog
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.db.client import check_database
from app.db.jobs import live_queued

POLL_SECONDS = 5.0


class LiveWakeup:
    """LIVE is a hint, never the source of truth; replace lost subscriptions."""

    def __init__(self, settings: Settings, wakeup: asyncio.Event) -> None:
        self.settings = settings
        self.wakeup = wakeup
        self.connection: AsyncWsSurrealConnection | None = None
        self.subscribed = asyncio.Event()

    async def listen(self) -> None:
        while True:
            try:
                await self._subscription()
                raise ConnectionError("LIVE subscription ended")
            except Exception as exc:
                structlog.get_logger().warning(
                    "worker_live_failed", error_type=type(exc).__name__, retry_in=POLL_SECONDS
                )
                self.wakeup.set()
                await asyncio.sleep(POLL_SECONDS)

    async def _subscription(self) -> None:
        settings = self.settings
        async with AsyncWsSurrealConnection(
            settings.surreal_url, timeout=settings.surreal_timeout_seconds, reconnect=False
        ) as db:
            self.connection = db
            async with asyncio.timeout(settings.surreal_timeout_seconds):
                await db.connect()
                await db.signin(
                    {"username": settings.surreal_user, "password": settings.surreal_pass}
                )
                await db.use(settings.surreal_namespace, settings.surreal_database)
                await check_database(db, settings.surreal_timeout_seconds)
                live_id = await live_queued(db)
                notifications = await db.subscribe_live(live_id)
            try:
                self.subscribed.set()
                self.wakeup.set()
                async for _notification in notifications:
                    self.wakeup.set()
            finally:
                self.subscribed.clear()
                self.connection = None
                # KILL may fail on a lost socket; context exit still closes all SDK tasks.
                try:
                    async with asyncio.timeout(settings.surreal_timeout_seconds):
                        await db.kill(live_id)
                except Exception as exc:
                    structlog.get_logger().warning(
                        "worker_live_cleanup_failed", error_type=type(exc).__name__
                    )
                with suppress(StopAsyncIteration):
                    await notifications.aclose()
