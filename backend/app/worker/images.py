from app.domain.jobs import Job, JobRejected
from app.services.pixabay import download
from app.worker.context import get_context


async def image(job: Job) -> None:
    if job.owner is None:
        raise JobRejected("image.owner_required")
    context = get_context()
    await download(context.db, context.settings, job.owner, job.payload)
