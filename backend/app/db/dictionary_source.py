"""Project typed lexicon records into the existing shared dictionary schema."""

from dataclasses import dataclass, field

from pydantic import JsonValue
from surrealdb import RecordID

from app.core.errors import AppError
from app.domain.dictionary_keys import DictionaryKey, lemma_key
from app.domain.lexicon import LexiconSense
from app.services.lexicon import LexiconReader


@dataclass
class SharedRow:
    record: RecordID
    fields: dict[str, JsonValue]


@dataclass
class SharedEdge:
    table: str
    start: RecordID
    end: RecordID
    fields: dict[str, JsonValue] = field(default_factory=dict)
    identity: list[str | int] = field(default_factory=list)

    @property
    def record(self) -> RecordID:
        return RecordID(self.table, [self.start, self.end, *self.identity])


@dataclass
class Materialization:
    lemma: RecordID
    lexemes: list[RecordID]
    senses: list[RecordID]
    rows: list[SharedRow]
    edges: list[SharedEdge]


async def relation_edges(reader: LexiconReader, sense: DictionaryKey) -> list[SharedEdge]:
    edges = []
    for direction in ("outgoing", "incoming"):
        for relation in await reader.relations(sense, direction=direction):
            edges.append(
                SharedEdge(
                    "relates_to",
                    RecordID("sense", relation.source_sense_id),
                    RecordID("sense", relation.target_sense_id),
                    {"type": relation.type, "source": relation.source},
                    [relation.type, relation.source],
                )
            )
    return edges


def _sense_fields(sense: LexiconSense) -> dict[str, JsonValue]:
    return {
        "definition": sense.definition,
        "gloss": {"zh": sense.gloss_zh} if sense.gloss_zh is not None else {},
        "register": [value for value in sense.registers],
        "domain": [value for value in sense.domain],
        "examples": [item["text"] for item in sense.examples if isinstance(item.get("text"), str)],
        "rank": sense.rank,
        "common": sense.common,
        "source": sense.source,
    }


async def prepare(
    reader: LexiconReader,
    key: DictionaryKey,
    selected_senses: list[DictionaryKey] | None,
) -> Materialization:
    lemma = await reader.get_lemma_by_id(key)
    if lemma is None:
        raise AppError("dictionary.not_found", 404, "Lexicon lemma not found.")
    lemma_id = RecordID("lemma", lemma.id)
    tags = await reader.tags(lemma.id)
    plan = Materialization(
        lemma_id,
        [],
        [],
        [
            SharedRow(
                lemma_id,
                {
                    "text": lemma.text,
                    "lang": lemma.lang,
                    "kind": lemma.kind,
                    "freq_zipf": lemma.freq_zipf if lemma.freq_zipf is not None else 0,
                    "cefr": lemma.cefr,
                    "exam_tags": [value for value in sorted({tag.tag for tag in tags})],
                    "source": lemma.source,
                },
            )
        ],
        [],
    )
    found: list[DictionaryKey] = []
    for lexeme in await reader.lexemes(lemma.id):
        lexeme_id = RecordID("lexeme", lexeme.id)
        plan.lexemes.append(lexeme_id)
        forms = await reader.forms(lexeme.id)
        pronunciations = await reader.pronunciations(lexeme.id)
        plan.rows.append(
            SharedRow(
                lexeme_id,
                {
                    "pos": lexeme.pos,
                    "etymology_no": lexeme.etymology_no,
                    "etymology_text": lexeme.etymology_text,
                    "forms": [
                        {"form": form.form, "tags": [tag for tag in form.tags]} for form in forms
                    ],
                    "pron": [
                        {"accent": pron.accent, "ipa": pron.ipa}
                        for pron in pronunciations
                        if pron.accent is not None and pron.ipa is not None
                    ],
                },
            )
        )
        plan.edges.append(SharedEdge("has_lexeme", lemma_id, lexeme_id))
        for affix in await reader.affixes(lexeme.id):
            morpheme = RecordID("morpheme", [*lemma_key(lemma.lang, affix.text), affix.type])
            plan.rows.append(SharedRow(morpheme, {"text": affix.text, "type": affix.type}))
            plan.edges.append(
                SharedEdge(
                    "composed_of",
                    lexeme_id,
                    morpheme,
                    {"order": affix.position},
                    [affix.position],
                )
            )
        for sense in await reader.senses(lexeme.id):
            chosen = sense.common if selected_senses is None else sense.id in selected_senses
            if not chosen:
                continue
            found.append(sense.id)
            sense_id = RecordID("sense", sense.id)
            plan.senses.append(sense_id)
            plan.rows.append(SharedRow(sense_id, _sense_fields(sense)))
            plan.edges.append(SharedEdge("has_sense", lexeme_id, sense_id, {"rank": sense.rank}))
            for domain in sense.domain:
                tag_id = RecordID("tag", ["domain", lemma_key(lemma.lang, domain)[1]])
                plan.rows.append(SharedRow(tag_id, {"kind": "domain", "name": domain}))
                plan.edges.append(SharedEdge("member_of", sense_id, tag_id))
            plan.edges.extend(await relation_edges(reader, sense.id))
    if selected_senses is not None and any(key not in found for key in selected_senses):
        raise AppError(
            "dictionary.invalid_selection", 422, "Selected senses must belong to this lemma."
        )
    return plan
