"""Enrich existing shared dictionary items without touching requester overlays."""

import structlog
from surrealdb import AsyncSurrealConnection

from app.db import enrichment as repository
from app.db.dictionary_enrichment_source import prepare_enrichment
from app.domain.add_to_project import EnrichJobPayload
from app.services.lexicon import LexiconReader


async def enrich(
    db: AsyncSurrealConnection, reader: LexiconReader, payload: EnrichJobPayload
) -> None:
    plan, fields = await prepare_enrichment(reader, payload)
    await repository.apply(db, plan, fields)
    structlog.get_logger().info("dictionary_enriched", lemma_id=payload.lemma_id)
