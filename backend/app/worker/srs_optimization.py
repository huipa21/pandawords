from app.domain.jobs import Job
from app.services.srs_optimization import optimize
from app.worker.context import get_context


async def srs_optimize(job: Job) -> None:
    if job.owner is not None:
        await optimize(get_context().db, job.owner)
