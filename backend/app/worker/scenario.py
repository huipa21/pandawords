from app.domain.jobs import Job
from app.services.scenario import generate_job
from app.worker.context import get_context


async def scenario(job: Job) -> None:
    context = get_context()
    await generate_job(context.db, context.settings, job)
