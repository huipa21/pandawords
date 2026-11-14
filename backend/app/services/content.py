"""Offline-first ingestion; optional suggestions never confirm senses."""

from typing import cast
from uuid import UUID

from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.core.errors import AppError, LlmUnavailable
from app.core.record_ids import decode_rid, encode_rid
from app.db import content as repository
from app.db import content_parts
from app.db.auth import _atomic
from app.db.dictionary_materialize import materialize
from app.db.dictionary_source import prepare
from app.domain.content import (
    AnalysisRead,
    ContentCreate,
    ContentKind,
    ContentRead,
    Occurrence,
    PassageRead,
    Resolution,
    SentencePart,
    Suggestion,
)
from app.domain.dictionary_keys import DictionaryKey
from app.services import llm, project_tree
from app.services.content_analysis import analyze, split
from app.services.lexicon import LexiconReader


def target(value: str, kind: str) -> RecordID:
    try:
        return decode_rid(value, kind)
    except ValueError:
        raise AppError("content.not_found", 404, "Content not found.") from None


def validate_fields(kind: ContentKind, data: ContentCreate) -> None:
    if kind == "sentence" and data.title:
        raise AppError("content.invalid_fields", 422, "Sentences have no title.")
    if kind == "passage" and data.translation:
        raise AppError("content.invalid_fields", 422, "Passages have no translation.")


async def create(
    db: AsyncSurrealConnection, owner: str, kind: ContentKind, data: ContentCreate
) -> ContentRead:
    validate_fields(kind, data)
    return await repository.create(db, owner, kind, data)


async def get(db: AsyncSurrealConnection, owner: str, kind: ContentKind, id: str) -> ContentRead:
    result = await repository.manage(db, owner, target(id, kind))
    assert result is not None
    return result


async def update(
    db: AsyncSurrealConnection, owner: str, kind: ContentKind, id: str, data: ContentCreate
) -> ContentRead:
    validate_fields(kind, data)
    result = await repository.manage(db, owner, target(id, kind), data)
    assert result is not None
    return result


async def delete(db: AsyncSurrealConnection, owner: str, kind: ContentKind, id: str) -> None:
    await repository.manage(db, owner, target(id, kind), delete=True)


async def occurrences(
    db: AsyncSurrealConnection, reader: LexiconReader, owner: str, sentence: ContentRead
) -> list[Occurrence]:
    matches = await analyze(reader, sentence.text, sentence.lang)
    links = await repository.links(db, owner, target(sentence.id, "sentence"))
    for occurrence in matches:
        for edge in links:
            if tuple(edge.get("span", ())) == occurrence.span:
                occurrence.status = "resolved"
                occurrence.sense_id = encode_rid(edge["in"], "sense")
                occurrence.edge_id = encode_rid(edge["id"], "used_in")
    return matches


async def passage(
    db: AsyncSurrealConnection,
    reader: LexiconReader,
    owner: str,
    id: str,
    project_id: str | None = None,
) -> PassageRead:
    item = await get(db, owner, "passage", id)
    parts = await repository.parts(db, owner, target(id, "passage"))
    sentences = []
    segments = split(item.text)
    for part in parts:
        sentence = repository.read(part["row"])
        order = part["order"]
        if not 0 <= order < len(segments) or segments[order][0] != sentence.text:
            raise AppError("content.stale_parts", 409, "Passage sentences have been edited.")
        sentences.append(
            SentencePart(
                sentence=sentence,
                order=order,
                span=segments[order][1],
                occurrences=await occurrences(db, reader, owner, sentence),
            )
        )
    result = PassageRead(passage=item, sentences=sentences)
    if project_id is not None:
        # Reuse the effective, owner-safe selection snapshot, including ancestor visibility.
        tree = await project_tree.read_tree(db, owner, project_id, 1, 10_000, False)
        result.project_senses = [
            node.sense
            for lemma in tree.items
            for lexeme in lemma.lexemes
            for node in lexeme.senses
            if not (lemma.effective_hidden or lexeme.effective_hidden or node.effective_hidden)
        ]
    return result


async def ingest(
    db: AsyncSurrealConnection, reader: LexiconReader, owner: str, data: ContentCreate
) -> PassageRead:
    validate_fields("passage", data)
    segments = split(data.text)
    parts = [ContentCreate(text=text, lang=data.lang, source=data.source) for text, _ in segments]
    analyzed = [await analyze(reader, part.text, part.lang) for part in parts]
    # Prepare only dictionary content, outside the write transaction.
    plans = {}
    for matches in analyzed:
        for occurrence in matches:
            if len(occurrence.candidates) == 1:
                candidate = occurrence.candidates[0]
                sense = target(candidate.sense_id, "sense")
                lexicon_sense = await reader.get_sense(cast(DictionaryKey, sense.id))
                assert lexicon_sense is not None
                lexeme = await reader.get_lexeme(lexicon_sense.lexeme_id)
                assert lexeme is not None
                plans[candidate.sense_id] = await prepare(
                    reader, lexeme.lemma_id, [cast(DictionaryKey, sense.id)]
                )

    async def link(sentence: RecordID, order: int, txn: UUID) -> None:
        existing = await repository.links(db, owner, sentence, txn)
        for occurrence in analyzed[order]:
            if len(occurrence.candidates) != 1:
                continue
            if any(tuple(edge.get("span", ())) == occurrence.span for edge in existing):
                continue
            candidate = occurrence.candidates[0]
            await materialize(db, plans[candidate.sense_id], txn_id=txn)
            await repository.resolve(
                db, owner, sentence, target(candidate.sense_id, "sense"), occurrence.span, txn
            )

    record = await repository.ingest(db, owner, data, parts, link)
    return await passage(db, reader, owner, encode_rid(record, "passage"))


async def resolve(
    db: AsyncSurrealConnection, reader: LexiconReader, owner: str, id: str, data: Resolution
) -> AnalysisRead:
    sentence = await get(db, owner, "sentence", id)
    matches = await analyze(reader, sentence.text, sentence.lang)
    if not any(item.span == data.span for item in matches):
        raise AppError("content.invalid_span", 422, "Span must identify a complete token.")
    sense = target(data.sense_id, "sense")

    async def operation(txn: UUID) -> None:
        # A visible custom sense may be explicitly confirmed, even if not in the offline lexicon.
        candidates = [
            candidate
            for item in matches
            if item.span == data.span
            for candidate in item.candidates
            if candidate.sense_id == data.sense_id
        ]
        if candidates:
            found = await reader.get_sense(cast(DictionaryKey, sense.id))
            assert found is not None
            lexeme = await reader.get_lexeme(found.lexeme_id)
            assert lexeme is not None
            await materialize(
                db,
                await prepare(reader, lexeme.lemma_id, [cast(DictionaryKey, sense.id)]),
                txn_id=txn,
            )
        current = repository.read(
            await repository.owned(db, repository.actor(owner), target(id, "sentence"), txn)
        )
        if current.text != sentence.text:
            raise AppError("content.changed", 409, "Sentence changed during resolution.")
        await repository.resolve(db, owner, target(id, "sentence"), sense, data.span, txn)

    await _atomic(db, operation)
    return AnalysisRead(
        sentence=sentence, occurrences=await occurrences(db, reader, owner, sentence)
    )


async def analysis(
    db: AsyncSurrealConnection,
    reader: LexiconReader,
    settings: Settings,
    owner: str,
    id: str,
    assist: bool,
) -> AnalysisRead:
    sentence = await get(db, owner, "sentence", id)
    result = AnalysisRead(
        sentence=sentence, occurrences=await occurrences(db, reader, owner, sentence)
    )
    if not assist:
        return result

    allowed = {
        (item.span, candidate.sense_id)
        for item in result.occurrences
        if item.status == "ambiguous"
        for candidate in item.candidates
    }
    if not allowed:
        result.assistance = "not_needed"
        return result
    try:
        suggested = await llm.generate_json(
            db,
            settings,
            user=owner,
            response_model=Suggestion,
            prompt="Suggest senses only from the provided candidates. Return resolutions with "
            "the original span and sense_id. Do not invent candidates.",
            prompt_version="content-senses-v1",
            schema_version="1",
            inputs={
                "text": sentence.text,
                "occurrences": [item.model_dump(mode="json") for item in result.occurrences],
            },
            validate=lambda value: all(
                (item.span, item.sense_id) in allowed for item in value.resolutions
            ),
        )
        result.suggestions = suggested.value.resolutions
        result.assistance = "available"
    except LlmUnavailable as error:
        result.assistance = f"unavailable:{error.reason}"
    return result


async def listing(
    db: AsyncSurrealConnection, owner: str, kind: ContentKind, limit: int, offset: int
) -> list[ContentRead]:
    return await repository.list_content(db, owner, kind, limit, offset)


async def remove_occurrence(db: AsyncSurrealConnection, owner: str, id: str, edge_id: str) -> None:
    await repository.delete_link(db, owner, target(id, "sentence"), target(edge_id, "used_in"))


async def assign_part(
    db: AsyncSurrealConnection, owner: str, id: str, sentence_id: str, order: int
) -> None:
    item = await get(db, owner, "passage", id)
    segments = split(item.text)
    if not 0 <= order < len(segments):
        raise AppError("content.invalid_part", 422, "Order must identify an original segment.")
    await content_parts.assign(
        db,
        owner,
        target(id, "passage"),
        target(sentence_id, "sentence"),
        order,
        segments[order][0],
        item.text,
    )


async def remove_part(db: AsyncSurrealConnection, owner: str, id: str, order: int) -> None:
    await content_parts.remove(db, owner, target(id, "passage"), order)
