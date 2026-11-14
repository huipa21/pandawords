from app.domain.add_to_project import EnrichJobPayload
from app.domain.jobs import Job
from app.services.enrichment import enrich as enrich_dictionary
from app.services.lexicon import LexiconReader
from app.worker.context import get_context


async def enrich(job: Job) -> None:
    context = get_context()
    settings = context.settings
    reader = LexiconReader(settings.lexicon_path or settings.lexicon_dir / "lexicon.sqlite")
    await enrich_dictionary(context.db, reader, EnrichJobPayload.model_validate(job.payload))
