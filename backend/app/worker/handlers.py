from collections.abc import Awaitable, Callable

from app.domain.jobs import Job
from app.worker.audio import audio
from app.worker.enrich import enrich
from app.worker.images import image
from app.worker.mnemonic import mnemonic
from app.worker.scenario import scenario

type Handler = Callable[[Job], Awaitable[None]]


async def noop(_job: Job) -> None:
    pass


HANDLERS: dict[str, Handler] = {
    "noop": noop,
    "audio": audio,
    "enrich": enrich,
    "scenario": scenario,
    "image": image,
    "mnemonic": mnemonic,
}
