"""Discover composition, not literal sense usage, without creating dictionary rows."""

from typing import Literal

from surrealdb import AsyncSurrealConnection

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db.phrases import containing_phrases as lookup
from app.domain.candidates import CandidateRequest
from app.domain.phrases import ContainingPhraseRead, ContainingPhrasesRead
from app.services import dictionary
from app.services.candidates import CandidateService
from app.services.lexicon import LexiconReader


async def containing_phrases(
    db: AsyncSurrealConnection,
    reader: LexiconReader,
    owner: str,
    table: Literal["lemma", "lexeme"],
    target: str,
    *,
    offset: int,
    limit: int,
) -> ContainingPhrasesRead:
    try:
        rid = decode_rid(target, table)
    except ValueError:
        raise AppError("dictionary.not_found", 404, "Word not found.") from None
    record = await dictionary.read_record(db, owner, target, table)
    if record is None:
        raise AppError("dictionary.not_found", 404, "Word not found.")
    ids = await lookup(db, owner, rid, offset=offset, limit=limit + 1)
    items: list[ContainingPhraseRead] = []
    sources = {}
    for phrase_id in ids[:limit]:
        entry = await dictionary.read_entry(db, owner, phrase_id)
        if entry is None:
            continue
        key = decode_rid(phrase_id, "lemma").id
        candidate = None
        if entry.lemma.owner is None and isinstance(key, list) and len(key) == 2:
            resolved = await CandidateService(reader).resolve(CandidateRequest(text=str(key[1])))
            candidate = next(
                (
                    item
                    for item in resolved.candidates
                    if item.lemma.kind == "phrase" and item.lemma.id == key
                ),
                None,
            )
            for source in resolved.sources:
                sources[source.name] = source
        items.append(ContainingPhraseRead(entry=entry, candidate=candidate))
    return ContainingPhrasesRead(
        items=items,
        sources=list(sources.values()),
        offset=offset,
        limit=limit,
        has_more=len(ids) > limit,
    )
