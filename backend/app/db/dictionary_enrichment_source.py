"""Source-backed enrichment plans; never recursively import related dictionary items."""

import structlog
from pydantic import JsonValue
from surrealdb import RecordID

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db.dictionary_source import Materialization, SharedEdge, relation_edges
from app.domain.add_to_project import EnrichJobPayload
from app.domain.dictionary_keys import DictionaryKey
from app.services.lexicon import LexiconReader
from app.services.morphology import prepare_morphology


async def _derivations(
    reader: LexiconReader, lexeme_key: DictionaryKey, lang: str
) -> list[SharedEdge]:
    affixes = await reader.affixes(lexeme_key)
    roots = [affix for affix in affixes if affix.type == "root"]
    modifiers = [affix for affix in affixes if affix.type != "root"]
    if len(roots) != 1 or not modifiers:
        return []
    root = roots[0]
    base = await reader.get_lemma(root.text, lang=lang)
    if base is None:
        structlog.get_logger().info("enrich_derivation_missing_base", lexeme_key=lexeme_key)
        return []
    bases = await reader.lexemes(base.id)
    if len(bases) != 1:
        structlog.get_logger().info("enrich_derivation_ambiguous_base", lexeme_key=lexeme_key)
        return []
    start, end = RecordID("lexeme", bases[0].id), RecordID("lexeme", lexeme_key)
    if start == end or any(affix.source != root.source for affix in modifiers):
        return []
    via = " ".join(affix.text for affix in modifiers)
    return [
        SharedEdge("derives_to", start, end, {"via": via, "source": root.source}, [root.source])
    ]


async def prepare_enrichment(
    reader: LexiconReader, payload: EnrichJobPayload
) -> tuple[Materialization, dict[str, JsonValue]]:
    lemma_id = decode_rid(payload.lemma_id, "lemma")
    lexeme_id = decode_rid(payload.lexeme_id, "lexeme")
    sense_id = decode_rid(payload.sense_id, "sense")
    lemma = await reader.get_lemma_by_id(payload.lemma_key)
    if lemma is None:
        raise AppError("dictionary.not_found", 404, "Enrichment source lemma not found.")
    lexemes = await reader.lexemes(lemma.id)
    lexeme = next((item for item in lexemes if RecordID("lexeme", item.id) == lexeme_id), None)
    sense = (
        next(
            (
                item
                for item in await reader.senses(lexeme.id)
                if RecordID("sense", item.id) == sense_id
            ),
            None,
        )
        if lexeme is not None
        else None
    )
    if lemma_id != RecordID("lemma", lemma.id) or lexeme is None or sense is None:
        raise AppError("dictionary.invalid_selection", 422, "Enrichment identities do not match.")

    edges = await relation_edges(reader, sense.id)
    edges.extend(await _derivations(reader, lexeme.id, lemma.lang))
    # Incoming derivations allow adding the base after its derived item was materialized.
    for root in await reader.affixes_for_root(lemma.text, lang=lemma.lang):
        edges.extend(await _derivations(reader, root.lexeme_id, lemma.lang))
    tags, frequencies = await reader.tags(lemma.id), await reader.frequencies(lemma.id)
    fields: dict[str, JsonValue] = {}
    if tags:
        fields["exam_tags"] = [tag for tag in sorted({item.tag for item in tags})]
        fields["exam_tag_sources"] = [{"tag": tag.tag, "source": tag.source} for tag in tags]
    if frequencies:
        fields["frequencies"] = [
            {"source": item.source, "zipf": item.zipf, "bnc": item.bnc, "coca": item.coca}
            for item in frequencies
        ]
        zipfs = {item.zipf for item in frequencies if item.zipf is not None}
        if len(zipfs) == 1:
            fields["freq_zipf"] = next(iter(zipfs))
        elif zipfs:
            structlog.get_logger().warning("enrich_frequency_conflict", lemma_key=lemma.id)
    missing = [
        name
        for name, present in (
            ("exam_tags", tags),
            ("frequencies", frequencies),
            ("relations", edges),
        )
        if not present
    ]
    if missing:
        structlog.get_logger().info(
            "enrich_optional_source_absent", lemma_key=lemma.id, fields=missing
        )
    rows, morphology_edges = await prepare_morphology(reader, lexeme.id, [sense_id])
    edges.extend(morphology_edges)
    return Materialization(lemma_id, [lexeme_id], [sense_id], rows, edges), fields
