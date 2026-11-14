import asyncio
import signal
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.worker.__main__ import main

pytestmark = pytest.mark.anyio


async def test_windows_signal_fallback_restores_handlers_after_cancellation() -> None:
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    loop = asyncio.get_running_loop()

    async def cancelled(_settings: Settings) -> None:
        raise asyncio.CancelledError

    with (
        patch("app.worker.__main__.run_worker", cancelled),
        patch.object(loop, "add_signal_handler", side_effect=NotImplementedError),
        patch.object(loop, "remove_signal_handler", side_effect=NotImplementedError),
    ):
        await main()
    assert {sig: signal.getsignal(sig) for sig in previous} == previous
