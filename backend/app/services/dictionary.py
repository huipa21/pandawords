"""Dictionary facade for API/services; routers need not import repositories."""

from typing import Literal
from uuid import UUID

from surrealdb import AsyncSurrealConnection

from app.core.record_ids import decode_rid
from app.db import dictionary as repository
from app.db.dictionary_materialize import materialize
from app.db.dictionary_source import prepare
from app.domain.dictionary import (
    DictionaryEdgeRead,
    DictionaryEntryRead,
    DictionaryRecordRead,
    DictionaryRelation,
    DictionaryTable,
    MaterializedDictionary,
)
from app.domain.dictionary_keys import DictionaryKey, lemma_key
from app.services.lexicon import LexiconReader


async def materialize_lemma(
    db: AsyncSurrealConnection,
    reader: LexiconReader,
    text: str,
    *,
    lang: str = "en",
    selected_senses: list[DictionaryKey] | None = None,
    txn_id: UUID | None = None,
) -> MaterializedDictionary:
    """None selects common senses; [] selects none; explicit keys select exactly those senses."""
    return await materialize(
        db, await prepare(reader, lemma_key(lang, text), selected_senses), txn_id=txn_id
    )


async def read_record(
    db: AsyncSurrealConnection, owner: str, rid: str, table: DictionaryTable
) -> DictionaryRecordRead | None:
    records = await repository.read_records(db, owner, [decode_rid(rid, table)])
    return records[0] if records else None


async def read_records(
    db: AsyncSurrealConnection, owner: str, targets: list[tuple[DictionaryTable, str]]
) -> list[DictionaryRecordRead]:
    return await repository.read_records(
        db, owner, [decode_rid(rid, table) for table, rid in targets]
    )


async def read_entry(
    db: AsyncSurrealConnection, owner: str, lemma_id: str
) -> DictionaryEntryRead | None:
    """All materialized visible senses, not a particular project's selected memberships."""
    return await repository.read_entry(db, owner, decode_rid(lemma_id, "lemma"))


async def read_edges(
    db: AsyncSurrealConnection,
    owner: str,
    rid: str,
    table: DictionaryTable,
    *,
    relation: DictionaryRelation | None = None,
    direction: Literal["outgoing", "incoming", "both"] = "both",
) -> list[DictionaryEdgeRead]:
    return await repository.read_edges(
        db, owner, decode_rid(rid, table), relation=relation, direction=direction
    )
