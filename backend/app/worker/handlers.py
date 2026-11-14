from collections.abc import Awaitable, Callable

from app.domain.jobs import Job
from app.worker.enrich import enrich

type Handler = Callable[[Job], Awaitable[None]]


async def noop(_job: Job) -> None:
    pass


HANDLERS: dict[str, Handler] = {"noop": noop, "enrich": enrich}
