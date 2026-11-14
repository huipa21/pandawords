import asyncio
import hashlib
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.core.errors import AppError
from app.domain.dictionary_keys import lemma_key, lexeme_key, sense_key
from app.domain.lexicon import LexiconLemma
from app.services.lexicon import LexiconReader

# isort: split
from scripts.build_fixture_lexicon import FIXTURES, build_fixture


async def test_exact_form_and_phrase_lookup(lexicon_reader: LexiconReader) -> None:
    await lexicon_reader.validate()
    run = await lexicon_reader.get_lemma("  ＲＵＮ ")
    assert isinstance(run, LexiconLemma)
    assert run.id == lemma_key("en", "run")
    assert await lexicon_reader.get_lemma_by_id(run.id) == run
    assert await lexicon_reader.lookup_form(" ＲＡＮ ") == [run]
    assert await lexicon_reader.get_lemma("ran") is None
    phrase = await lexicon_reader.get_lemma("give   UP")
    assert phrase is not None and phrase.kind == "phrase"
    assert await lexicon_reader.lookup_form("gave up") == [phrase]
    bucket = await lexicon_reader.get_lemma("kick the bucket")
    assert bucket is not None and bucket.kind == "phrase"
    assert await lexicon_reader.lookup_form("kicked the bucket") == [bucket]
    idiom_senses = await lexicon_reader.senses(lexeme_key("en", "kick the bucket", "verb"))
    assert idiom_senses[0].registers == ["informal"]
    assert await lexicon_reader.get_lemma("not-a-fixture-word") is None
    assert await lexicon_reader.lookup_form("not-a-fixture-word") == []
    assert await lexicon_reader.get_lemma("run", lang="zh") is None
    assert await lexicon_reader.get_lemma("run' OR 1 = 1 --") is None


async def test_polysemy_inflections_and_senses(lexicon_reader: LexiconReader) -> None:
    run = lemma_key("en", "run")
    assert [item.pos for item in await lexicon_reader.lexemes(run)] == ["noun", "verb"]
    verbs = await lexicon_reader.lexemes(run, pos="verb")
    assert len(verbs) == 1
    verb = verbs[0]
    assert await lexicon_reader.get_lexeme(verb.id) == verb
    senses = await lexicon_reader.senses(verb.id)
    assert [sense.source_id for sense in senses] == ["run-move", "run-operate", "run-flow"]
    assert [sense.common for sense in senses] == [True, True, False]
    assert await lexicon_reader.senses(verb.id, common_only=True) == senses[:2]
    assert await lexicon_reader.get_sense(senses[0].id) == senses[0]
    assert senses[0].examples == [{"text": "We run every morning."}]
    assert senses[0].domain == ["motion"] and senses[0].lexname == "verb.motion"
    assert {form.form for form in await lexicon_reader.forms(verb.id)} == {"ran", "running", "runs"}
    bank = await lexicon_reader.lexemes(lemma_key("en", "bank"))
    assert [item.etymology_no for item in bank] == [1, 2]
    assert "river" in (await lexicon_reader.senses(bank[1].id))[0].definition
    unknown = lexeme_key("en", "absent", "verb")
    assert await lexicon_reader.get_lexeme(unknown) is None
    assert await lexicon_reader.senses(unknown) == []
    assert await lexicon_reader.get_sense([*unknown, "missing"]) is None


async def test_pronunciations_glosses_tags_and_frequency(lexicon_reader: LexiconReader) -> None:
    for word in ("schedule", "tomato"):
        lexeme = lexeme_key("en", word, "noun")
        pronunciations = await lexicon_reader.pronunciations(lexeme)
        assert {item.accent for item in pronunciations} == {"US", "UK"}
        us = await lexicon_reader.pronunciations(lexeme, accent="US")
        uk = await lexicon_reader.pronunciations(lexeme, accent="UK")
        assert len(us) == len(uk) == 1 and us[0].ipa != uk[0].ipa
    glosses = await lexicon_reader.glosses(lexeme_key("en", "run", "verb"))
    assert {gloss.gloss for gloss in glosses} == {"跑", "经营"}
    assert any(gloss.sense_id is not None for gloss in glosses)
    lemma = lemma_key("en", "run")
    assert {tag.tag for tag in await lexicon_reader.tags(lemma)} == {"cet4", "cet6"}
    frequencies = {item.source: item for item in await lexicon_reader.frequencies(lemma)}
    assert frequencies["ecdict"].bnc == 100 and frequencies["ecdict"].coca == 120
    run = await lexicon_reader.get_lemma("run")
    assert run is not None and run.freq_zipf == frequencies["wordfreq"].zipf == 5.4
    assert await lexicon_reader.lookup_form("children") == [await lexicon_reader.get_lemma("child")]
    sources = {source.name: source.metadata for source in await lexicon_reader.sources()}
    assert {"wiktionary", "ecdict", "wordfreq", "oewn", "oewn:approx"} <= sources.keys()
    assert sources["wordfreq"]["version"] == "synthetic-fixture-v1"


async def test_relations_are_directional_and_typed(lexicon_reader: LexiconReader) -> None:
    run = sense_key("en", "run", "verb", source_sense_id="run-move")
    move = sense_key("en", "move", "verb", source_sense_id="move-position")
    relations = await lexicon_reader.relations(run, type="hypernym")
    assert len(relations) == 1
    assert relations[0].target_sense_id == move and relations[0].source == "oewn"
    assert relations[0] in await lexicon_reader.relations(move, direction="incoming")
    assert await lexicon_reader.relations(run, type="antonym") == []
    happy = sense_key("en", "happy", "adj", source_sense_id="happy-pleased")
    related = await lexicon_reader.relations(happy)
    assert {(item.type, item.target_sense_id[1]) for item in related} == {
        ("synonym", "joyful"),
        ("antonym", "sad"),
    }


async def test_derivation_and_reserved_affix_reads(lexicon_reader: LexiconReader) -> None:
    decide = await lexicon_reader.get_lexeme(lexeme_key("en", "decide", "verb"))
    decision = await lexicon_reader.get_lexeme(lexeme_key("en", "decision", "noun"))
    assert decide is not None and decision is not None
    assert "decide" in (decision.etymology_text or "")
    assert await lexicon_reader.affixes(decision.id) == []


async def test_affix_rows_decode_structured_keys(tmp_path: Path) -> None:
    output = tmp_path / "affixes.sqlite"
    shutil.copyfile(FIXTURES / "lexicon_small.sqlite", output)
    with closing(sqlite3.connect(output)) as connection:
        connection.executemany(
            "INSERT INTO affix VALUES (?, ?, ?, ?, 'wiktionary')",
            [
                ('["en","decision","noun",1]', 1, "-ion", "suffix"),
                ('["en","decision","noun",1]', 0, "decis", "root"),
            ],
        )
        connection.commit()
    key = lexeme_key("en", "decision", "noun")
    affixes = await LexiconReader(output).affixes(key)
    assert [(item.text, item.type) for item in affixes] == [("decis", "root"), ("-ion", "suffix")]
    assert all(item.lexeme_id == key for item in affixes)


async def test_readonly_and_concurrent_reads(tmp_path: Path) -> None:
    output = tmp_path / "lexicon # readonly.sqlite"
    shutil.copyfile(FIXTURES / "lexicon_small.sqlite", output)
    before = hashlib.sha256(output.read_bytes()).digest()
    modified = output.stat().st_mtime_ns
    connect = sqlite3.connect
    opened = 0

    def readonly_probe(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        nonlocal opened
        connection = connect(*args, **kwargs)
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                connection.execute("DELETE FROM lemma")
        except BaseException:
            connection.close()
            raise
        opened += 1
        return connection

    reader = LexiconReader(output)
    with patch("app.services.lexicon.sqlite3.connect", side_effect=readonly_probe):
        await reader.validate()
        results = await asyncio.gather(*(reader.get_lemma(word) for word in ("run", "bank", "dog")))
    assert all(results) and opened == 4
    assert hashlib.sha256(output.read_bytes()).digest() == before
    assert output.stat().st_mtime_ns == modified
    children = await asyncio.to_thread(lambda: sorted(path.name for path in tmp_path.iterdir()))
    assert children == [output.name]
    output.unlink()  # No persistent reader handle prevents replacement/deletion on Windows.


async def test_missing_database_does_not_get_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    reader = LexiconReader(missing)
    for operation in (reader.validate, lambda: reader.get_lemma("run")):
        with pytest.raises(AppError, match="missing") as error:
            await operation()
        assert error.value.code == "lexicon.missing" and error.value.status == 503
    assert not missing.exists()


@pytest.mark.parametrize("kind", ["garbage", "empty", "wrong-version", "incomplete", "bad-column"])
async def test_invalid_database_errors(tmp_path: Path, kind: str) -> None:
    output = tmp_path / "invalid.sqlite"
    if kind == "garbage":
        output.write_bytes(b"not a SQLite artifact")
    elif kind in {"empty", "incomplete"}:
        with closing(sqlite3.connect(output)) as connection:
            if kind == "incomplete":
                connection.execute("PRAGMA user_version = 1")
    else:
        shutil.copyfile(FIXTURES / "lexicon_small.sqlite", output)
        with closing(sqlite3.connect(output)) as connection:
            if kind == "wrong-version":
                connection.execute("PRAGMA user_version = 2")
            else:
                connection.execute("ALTER TABLE lemma RENAME COLUMN cefr TO unexpected")
            connection.commit()
    with pytest.raises(AppError, match="Invalid lexicon database") as error:
        await LexiconReader(output).validate()
    assert error.value.code == "lexicon.invalid" and error.value.status == 503


async def test_invalid_record_data_becomes_domain_error(tmp_path: Path) -> None:
    output = tmp_path / "invalid-data.sqlite"
    shutil.copyfile(FIXTURES / "lexicon_small.sqlite", output)
    with closing(sqlite3.connect(output)) as connection:
        connection.execute("UPDATE sense SET examples = '[1]'")
        connection.commit()
    with pytest.raises(AppError, match="Invalid lexicon database") as error:
        await LexiconReader(output).senses(lexeme_key("en", "run", "verb"))
    assert error.value.code == "lexicon.invalid"


def test_fixture_rebuild_matches_committed_logical_database(tmp_path: Path) -> None:
    output = tmp_path / "rebuilt.sqlite"
    result = build_fixture(output)
    assert result.records == 52 and result.skipped_senses == 0
    with (
        closing(sqlite3.connect(output)) as rebuilt,
        closing(sqlite3.connect(FIXTURES / "lexicon_small.sqlite")) as committed,
    ):
        assert rebuilt.execute("SELECT COUNT(*) FROM lemma").fetchone() == (50,)
        assert list(rebuilt.iterdump()) == list(committed.iterdump())
