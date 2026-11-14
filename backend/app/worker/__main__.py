import asyncio
import signal
from contextlib import suppress

from app.core.config import Settings
from app.core.logging import configure_logging
from app.worker.runtime import run_worker


async def main() -> None:
    settings = Settings()
    configure_logging(settings.app_env)
    worker = asyncio.create_task(run_worker(settings), name="worker")
    loop = asyncio.get_running_loop()
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, worker.cancel)
            except NotImplementedError:
                signal.signal(sig, lambda _signum, _frame: loop.call_soon_threadsafe(worker.cancel))
        with suppress(asyncio.CancelledError):
            await worker
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.remove_signal_handler(sig)
            signal.signal(sig, previous[sig])


if __name__ == "__main__":
    asyncio.run(main())
