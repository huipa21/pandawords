"""Daily scheduled site backups for the `backup` Compose service."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, time, timedelta

import structlog

from app.core.config import Settings
from app.domain.site_backup import SiteBackupError
from app.services.site_backup import create_backup


def next_run(now: datetime, at: str) -> datetime:
    hour, minute = (int(part) for part in at.split(":"))
    current = now.astimezone(UTC)
    candidate = datetime.combine(current.date(), time(hour, minute), tzinfo=UTC)
    return candidate if candidate > current else candidate + timedelta(days=1)


async def run_schedule(
    settings: Settings,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    iterations: int | None = None,
) -> None:
    """Back up once per day at SITE_BACKUP_TIME (UTC); a failed run keeps prior backups."""
    log = structlog.get_logger()
    completed = 0
    while iterations is None or completed < iterations:
        due = next_run(clock(), settings.site_backup_time)
        log.info("site_backup_scheduled", due=due.isoformat())
        while (remaining := (due - clock()).total_seconds()) > 0:
            await sleep(min(remaining, 3600.0))
        try:
            await create_backup(settings, "scheduled")
        except SiteBackupError as error:
            log.error("site_backup_scheduled_failed", stage=error.stage)
        completed += 1
