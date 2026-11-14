"""Enrich existing shared dictionary items without touching requester overlays."""

from typing import cast

import structlog
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.db import enrichment as repository
from app.db.dictionary_enrichment_source import prepare_enrichment
from app.domain.add_to_project import EnrichJobPayload
from app.domain.dictionary_keys import DictionaryKey
from app.services.lexicon import LexiconReader


async def enrich(
    db: AsyncSurrealConnection,
    reader: LexiconReader,
    payload: EnrichJobPayload,
    *,
    llm_settings: Settings | None = None,
    user: str | None = None,
) -> None:
    plan, fields = await prepare_enrichment(reader, payload)
    if llm_settings is not None and user is not None:
        from app.services.morphology import prepare_morphology, propose

        lexeme = cast(DictionaryKey, plan.lexemes[0].id)
        proposal = await propose(db, llm_settings, reader, user, lexeme)
        if proposal is not None:
            rows, edges = await prepare_morphology(reader, lexeme, plan.senses, proposal)
            plan.rows.extend(rows)
            plan.edges.extend(edges)
    await repository.apply(db, plan, fields)
    structlog.get_logger().info("dictionary_enriched", lemma_id=payload.lemma_id)
