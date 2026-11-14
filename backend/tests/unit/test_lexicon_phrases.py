import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.domain.dictionary_keys import lemma_key, lexeme_key, sense_key
from app.services.lexicon import LexiconReader

# isort: split
from scripts.build_lexicon import build

# isort: split
from tests.unit.test_build_lexicon import entry, source_file


def compound(*words: str, **args: str) -> dict[str, Any]:
    return {
        "name": "compound",
        "args": {"1": "en", **{str(i + 2): word for i, word in enumerate(words)}, **args},
    }


async def test_order_identity_provenance_and_literal_evidence(tmp_path: Path) -> None:
    records = [
        entry("rain rain", etymology_templates=[compound("rain", "rain")]),
        entry("heavy rain", etymology_templates=[compound("heavy", "rain")]),
        entry("unknown phrase"),  # no source structure: never split the text
        entry(
            "heavy",
            pos="adj",
            senses=[
                {
                    "id": "intense",
                    "glosses": ["intense"],
                    "examples": [{"text": "HEAVY  RAIN", "tags": ["literal"]}],
                },
                {
                    "id": "weight",
                    "glosses": ["weighty"],
                    "examples": [{"text": "heavy rain"}],
                },
            ],
        ),
        entry("rain", pos="noun"),
    ]
    first, second = tmp_path / "first.sqlite", tmp_path / "second.sqlite"
    result = build(source_file(tmp_path, *records), first)
    build(source_file(tmp_path, *reversed(records)), second)
    assert result.skipped_phrase_mappings == 0
    reader = LexiconReader(first)
    await reader.validate()
    phrase = lemma_key("en", "heavy rain")
    components = await reader.phrase_components(phrase)
    assert [(item.lexeme_id, item.position, item.source) for item in components] == [
        (lexeme_key("en", "heavy", "adj"), 0, "wiktionary"),
        (lexeme_key("en", "rain", "noun"), 1, "wiktionary"),
    ]
    assert components == await LexiconReader(second).phrase_components(phrase)
    assert all(item.phrase_id == phrase for item in components)
    assert await reader.phrase_components(lemma_key("en", "unknown phrase")) == []
    repeated = await reader.phrase_components(lemma_key("en", "rain rain"))
    assert [item.position for item in repeated] == [0, 1]
    assert repeated[0].lexeme_id == repeated[1].lexeme_id
    usages = await reader.phrase_usages(phrase)
    assert len(usages) == 1
    assert usages[0].sense_id == sense_key("en", "heavy", "adj", source_sense_id="intense")
    assert usages[0].source == "wiktionary"
    assert usages == await LexiconReader(second).phrase_usages(phrase)
    with sqlite3.connect(first) as connection:
        metadata = json.loads(
            connection.execute("SELECT metadata FROM source WHERE name='wiktionary'").fetchone()[0]
        )
    assert metadata["sha256"] and metadata["license"] == "CC-BY-SA-4.0"


@pytest.mark.parametrize(
    ("templates", "extra", "reason"),
    [
        ([compound("rain", "missing")], [], "missing_component"),
        ([compound("rain", "heavy")], [entry("rain", pos="verb")], "ambiguous_component"),
        (
            [compound("rain", "heavy")],
            [entry("rain", pos="noun", etymology_number=2)],
            "ambiguous_component",
        ),
        ([compound("rain", "heavy"), compound("heavy", "rain")], [], "conflicting_templates"),
        ([compound("rain", "heavy", lang2="fr")], [], "unsupported_template"),
        ([compound("[[rain]]", "heavy")], [], "unsupported_template"),
        ([compound(*(["rain"] * 33))], [], "unsupported_template"),
        ([compound("rain", "heavy", **{"4": "missing", "5": ""})], [], "missing_component"),
    ],
)
async def test_unresolved_composition_is_atomic_and_diagnosed(
    tmp_path: Path,
    templates: list[dict[str, Any]],
    extra: list[dict[str, Any]],
    reason: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = source_file(
        tmp_path,
        entry("rain heavy", etymology_templates=templates),
        entry("rain", pos="noun"),
        entry("heavy", pos="adj"),
        *extra,
    )
    output = tmp_path / "lexicon.sqlite"
    result = build(source, output)
    assert result.skipped_phrase_mappings > 0
    assert reason in capsys.readouterr().out
    assert await LexiconReader(output).phrase_components(lemma_key("en", "rain heavy")) == []


async def test_fixture_phrase_meanings_and_literal_senses_are_separate(
    lexicon_reader: LexiconReader,
) -> None:
    idiom = lemma_key("en", "kick the bucket")
    components = await lexicon_reader.phrase_components(idiom)
    assert [item.lexeme_id for item in components] == [
        lexeme_key("en", "kick", "verb"),
        lexeme_key("en", "the", "article"),
        lexeme_key("en", "bucket", "noun"),
    ]
    assert await lexicon_reader.phrase_usages(idiom) == []
    senses = await lexicon_reader.senses(lexeme_key("en", "kick the bucket", "verb"))
    assert senses[0].definition == "Die." and "idiomatic" in senses[0].tags
    assert len(await lexicon_reader.phrase_usages(lemma_key("en", "heavy rain"))) == 2
