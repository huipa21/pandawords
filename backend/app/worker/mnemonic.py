from app.domain.jobs import Job
from app.services.mnemonics import generate_job
from app.worker.context import get_context


async def mnemonic(job: Job) -> None:
    context = get_context()
    await generate_job(context.db, context.settings, job)
