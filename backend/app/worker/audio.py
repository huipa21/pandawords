from app.domain.add_to_project import AudioJobPayload
from app.domain.jobs import Job
from app.services.audio import acquire
from app.services.lexicon import LexiconReader
from app.worker.context import get_context


async def audio(job: Job) -> None:
    context = get_context()
    settings = context.settings
    reader = LexiconReader(settings.lexicon_path or settings.lexicon_dir / "lexicon.sqlite")
    await acquire(context.db, settings, reader, AudioJobPayload.model_validate(job.payload))
