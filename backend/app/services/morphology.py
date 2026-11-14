"""Validated morphology plans, shared by source and optional LLM enrichment."""

from typing import Literal, cast

import structlog
from pydantic import BaseModel, ConfigDict, Field
from surrealdb import AsyncSurrealConnection, RecordID

from app.core.config import Settings
from app.core.errors import LlmUnavailable
from app.db.dictionary_source import SharedEdge, SharedRow
from app.domain.dictionary_keys import DictionaryKey
from app.domain.morphology import MorphemeRead, MorphGroupMemberRead, component_order_valid
from app.services.lexicon import LexiconReader


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    position: int = Field(ge=0, lt=16)
    text: str
    type: Literal["root", "prefix", "suffix", "infix"]
    identity: DictionaryKey


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    components: list[Component] = Field(max_length=16)


async def resolve(
    reader: LexiconReader, text: str, kind: str
) -> tuple[RecordID, str | None] | None:
    lemma = await reader.get_lemma(text)
    if lemma is None:
        return None
    lexemes = await reader.lexemes(lemma.id)
    matches = [
        item
        for item in lexemes
        if (
            item.pos == kind
            if kind != "root"
            else item.pos not in {"prefix", "suffix", "infix", "affix"}
        )
    ]
    etymologies = {item.etymology_no for item in matches}
    if len(etymologies) != 1:
        return None
    # POS variants with one source etymology share a morpheme identity.
    identity: DictionaryKey = ["en", lemma.text, kind, next(iter(etymologies))]
    senses = [sense for item in matches for sense in await reader.senses(item.id)]
    if not senses:
        return None
    senses.sort(key=lambda sense: (sense.rank, str(sense.id)))
    return RecordID("morpheme", identity), senses[0].definition


async def prepare_morphology(
    reader: LexiconReader,
    lexeme: DictionaryKey,
    senses: list[RecordID],
    proposal: Proposal | None = None,
) -> tuple[list[SharedRow], list[SharedEdge]]:
    analysis = await reader.morphology_analysis(lexeme)
    status = analysis.status if analysis else "rejected"
    affixes = await reader.affixes(lexeme)
    source = "wiktionary"
    if status == "rejected":
        structlog.get_logger().info(
            "morphology_skipped", lexeme=lexeme, reason=analysis.reason if analysis else status
        )
        return [], []
    if status == "absent":
        if proposal is None or not proposal.components:
            return [], []
        components = proposal.components
        source = "llm:morphology-v1"
    else:
        if proposal is not None:
            return [], []
        if (
            analysis is None
            or analysis.source != source
            or any(part.source != source for part in affixes)
            or [[part.text, part.type] for part in affixes] != analysis.components
        ):
            structlog.get_logger().info(
                "morphology_skipped", lexeme=lexeme, reason="conflicting_source_rows"
            )
            return [], []
        components = [
            Component(position=part.position, text=part.text, type=part.type, identity=[])
            for part in affixes
        ]
    if (
        not 2 <= len(components) <= 16
        or [part.position for part in components] != list(range(len(components)))
        or not component_order_valid([part.type for part in components])
    ):
        structlog.get_logger().info("morphology_skipped", lexeme=lexeme, reason="invalid_order")
        return [], []
    resolved: list[tuple[Component, RecordID, str | None]] = []
    for part in components:
        match = await resolve(reader, part.text, part.type)
        if (
            match is None
            or part.text != cast(DictionaryKey, match[0].id)[1]
            or (status == "absent" and part.identity != match[0].id)
        ):
            structlog.get_logger().info(
                "morphology_skipped", lexeme=lexeme, reason="missing_or_ambiguous_identity"
            )
            return [], []
        resolved.append((part, *match))
    rows: dict[str, SharedRow] = {}
    edges = []
    for part, morpheme, meaning in resolved:
        tag = RecordID("tag", ["morph_group", *cast(DictionaryKey, morpheme.id)])
        rows[str(morpheme)] = SharedRow(
            morpheme,
            {"text": part.text, "type": part.type, "meaning": meaning, "source": "wiktionary"},
        )
        rows[str(tag)] = SharedRow(tag, {"name": part.text, "kind": "morph_group"})
        edges.append(
            SharedEdge(
                "composed_of",
                RecordID("lexeme", lexeme),
                morpheme,
                {"order": part.position, "source": source},
                [source, part.position],
            )
        )
        for member in [morpheme, *senses]:
            edges.append(SharedEdge("member_of", member, tag, {"source": source}, [source]))
    return list(rows.values()), edges


async def propose(
    db: AsyncSurrealConnection,
    settings: Settings,
    reader: LexiconReader,
    user: str,
    lexeme: DictionaryKey,
) -> Proposal | None:
    """Optional fallback: shared inputs only; no provider use when any source template exists."""
    from app.services.llm import generate_json

    analysis = await reader.morphology_analysis(lexeme)
    if analysis is None or analysis.status != "absent":
        return None

    try:
        result = await generate_json(
            db,
            settings,
            user=user,
            response_model=Proposal,
            prompt=(
                "Propose English morphemes only when unambiguous. Return components [] when "
                "uncertain. Each component has zero-based position, text (hyphenated affixes), "
                "type root/prefix/suffix/infix, identity [en,text,type,etymology_number]. "
                "Preserve actual order and repeats. Never merely segment matching letters."
            ),
            prompt_version="morphology-v1",
            schema_version="1",
            shared_sources=(RecordID("lexeme", lexeme),),
        )
        return result.value
    except LlmUnavailable as error:
        structlog.get_logger().info("morphology_llm_unavailable", reason=error.reason)
        return None


async def read_morphemes(
    db: AsyncSurrealConnection, user: str, lexeme_id: str
) -> list[MorphemeRead]:
    from app.core.record_ids import decode_rid
    from app.db.morphology import lexeme_morphemes

    return await lexeme_morphemes(db, user, decode_rid(lexeme_id, "lexeme"))


async def read_group_members(
    db: AsyncSurrealConnection,
    user: str,
    target_id: str,
    table: Literal["sense", "morpheme"],
    *,
    limit: int = 100,
) -> list[MorphGroupMemberRead]:
    from app.core.record_ids import decode_rid
    from app.db.morphology import group_members

    return await group_members(db, user, decode_rid(target_id, table), limit=limit)
