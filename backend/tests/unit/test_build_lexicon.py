import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.domain.dictionary_keys import lemma_key, lexeme_key, sense_key

# isort: split
from scripts.build_lexicon import build, main
from scripts.lexicon_kaikki import entries, key_text
from scripts.lexicon_schema import SCHEMA_VERSION


def entry(word: str = "run", **fields: Any) -> dict[str, Any]:
    return {
        "word": word,
        "lang_code": "en",
        "pos": "verb",
        "senses": [{"glosses": ["move quickly"]}],
        **fields,
    }


def source_file(tmp_path: Path, *records: dict[str, Any]) -> Path:
    source = tmp_path / "kaikki-english.jsonl"
    source.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return source


def dump(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as connection:
        return list(connection.iterdump())


def test_core_schema_keys_senses_forms_and_attribution(tmp_path: Path) -> None:
    source = source_file(
        tmp_path,
        entry(
            "ＲＵＮ",
            etymology_text="From Old English.",
            senses=[
                {
                    "id": "run-en-verb-Stable",
                    "glosses": ["move quickly", "travel on foot"],
                    "tags": ["informal"],
                    "topics": ["sports"],
                    "examples": [{"text": "Run home.", "ref": "Wiktionary"}],
                },
                {"glosses": ["operate a machine"]},
            ],
            sounds=[
                {
                    "ipa": "/ɹʌn/",
                    "tags": ["US"],
                    "audio": "En-us-run.ogg",
                    "ogg_url": "https://example.test/run.ogg",
                    "license": "CC-BY-SA",
                    "attribution": "A speaker",
                },
                {"ipa": "/rʌn/", "tags": ["UK"]},
                {"ipa": "/ɹʌn/", "tags": ["General-American", "Received-Pronunciation"]},
                {"audio": "run.mp3", "mp3_url": "https://example.test/run.mp3"},
            ],
            forms=[{"form": "ＲＡＮ", "tags": ["past"]}],
        ),
        entry(pos="noun", senses=[{"glosses": ["an act of running"]}]),
        entry(etymology_number="2", senses=[{"glosses": ["a distinct origin"]}]),
        entry(" ", pos="punct"),
        entry("kick the bucket", senses=[{"glosses": ["to die"]}]),
        entry("went", senses=[{"glosses": ["past of go"], "form_of": [{"word": "go"}]}]),
        entry("go", senses=[{"glosses": ["move"]}]),
    )
    output = tmp_path / "lexicon.sqlite"
    result = build(source, output)
    assert result.records == 6 and result.skipped_senses == 1
    with closing(sqlite3.connect(output)) as db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {
            "source",
            "lemma",
            "lexeme",
            "sense",
            "pron",
            "form",
            "form_index",
            "zh_gloss",
            "exam_tag",
            "freq",
            "relation",
            "affix",
            "morphology_analysis",
            "phrase_component",
            "phrase_usage",
        }
        lemma_id = key_text(lemma_key("en", "run"))
        lexeme_id = key_text(lexeme_key("en", "run", "verb", 1))
        assert db.execute(
            "SELECT COUNT(*) FROM lexeme WHERE lemma_id=?", (lemma_id,)
        ).fetchone() == (3,)
        sense_id = key_text(sense_key("en", "run", "verb", source_sense_id="run-en-verb-Stable"))
        sense = db.execute(
            "SELECT lexeme_id, glosses, register, domain, examples, rank, source "
            "FROM sense WHERE id=?",
            (sense_id,),
        ).fetchone()
        assert sense[:1] == (lexeme_id,)
        assert json.loads(sense[1]) == ["move quickly", "travel on foot"]
        assert json.loads(sense[2]) == ["informal"]
        assert json.loads(sense[3]) == ["sports"]
        assert json.loads(sense[4])[0]["text"] == "Run home."
        assert sense[5:] == (1, "wiktionary")
        for form, lemma in [("ran", "run"), ("run", "run"), ("went", "go")]:
            assert db.execute(
                "SELECT 1 FROM form_index WHERE form=? AND lemma_id=?",
                (form, key_text(lemma_key("en", lemma))),
            ).fetchone() == (1,)
        assert db.execute("SELECT kind FROM lemma WHERE text='kick the bucket'").fetchone() == (
            "phrase",
        )
        sounds = db.execute("SELECT accent, ipa, audio FROM pron ORDER BY id").fetchall()
        assert {row[0] for row in sounds} == {"US", "UK", None}
        assert len(sounds) == 5
        audio = next(json.loads(row[2]) for row in sounds if "license" in json.loads(row[2]))
        assert audio["license"] == "CC-BY-SA" and audio["attribution"] == "A speaker"
        metadata = json.loads(db.execute("SELECT metadata FROM source").fetchone()[0])
        assert metadata["license"] == "CC-BY-SA-4.0"
        assert "Wiktionary contributors" in metadata["attribution"]
        assert len(metadata["sha256"]) == 64
        plan = str(
            db.execute(
                "EXPLAIN QUERY PLAN SELECT lemma_id FROM form_index WHERE form='ran'"
            ).fetchall()
        )
        assert "SEARCH" in plan and "INDEX" in plan


def test_stable_keys_rebuild_duplicates_and_missing_optional_fields(tmp_path: Path) -> None:
    record = entry(
        senses=[
            {"id": "fixed-ID", "glosses": ["move quickly"]},
            {"glosses": [" OPERATE   a machine "]},
            {},
            None,
            {"glosses": []},
            {"glosses": [None, ""]},
            {"id": " ", "raw_glosses": ["raw fallback"]},
        ],
        sounds=[None, {}],
        forms=[{}, {"form": ""}],
    )
    source = source_file(tmp_path, record, record)
    first, second = tmp_path / "first.sqlite", tmp_path / "second.sqlite"
    assert build(source, first).skipped_senses == 8
    build(source, second)
    assert dump(first) == dump(second)
    with closing(sqlite3.connect(first)) as db:
        ids = {row[0] for row in db.execute("SELECT id FROM sense")}
        assert key_text(sense_key("en", "run", "verb", gloss="operate a machine")) in ids
        fixed = key_text(sense_key("en", "run", "verb", source_sense_id="fixed-ID"))
        assert fixed in ids and len(ids) == 3
    record["senses"][0]["glosses"] = ["a revised definition"]
    source_file(tmp_path, record)
    build(source, second)
    with closing(sqlite3.connect(second)) as db:
        assert db.execute("SELECT definition FROM sense WHERE id=?", (fixed,)).fetchone() == (
            "a revised definition",
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"{bad json\n",
        b"[]\n",
        b"",
        b'{"word":"incomplete"}\n',
        json.dumps(entry(lang_code="zh")).encode(),
        json.dumps(entry(pos=" ")).encode(),
        json.dumps(entry(etymology_number=0)).encode(),
        json.dumps(entry(etymology_number="first")).encode(),
        json.dumps(entry(etymology_number=True)).encode(),
        json.dumps(entry(senses={})).encode(),
        json.dumps(entry(senses=[{}])).encode(),
        b"\xff\n",
    ],
)
def test_invalid_build_never_replaces_output(tmp_path: Path, payload: bytes) -> None:
    source = source_file(tmp_path, entry())
    output = tmp_path / "lexicon.sqlite"
    build(source, output)
    before = output.read_bytes()
    source.write_bytes(payload)
    with pytest.raises(ValueError):
        build(source, output)
    assert output.read_bytes() == before
    assert not list(tmp_path.glob(".*.part*"))


def test_streaming_is_lazy_and_limits_line_size(tmp_path: Path) -> None:
    payload = (json.dumps(entry()) + "\n").encode()

    class BoundedFile(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            pytest.fail("whole-file read is forbidden")

        def readline(self, size: int | None = -1) -> bytes:
            assert size is not None and 0 < size <= len(payload) + 1
            return super().readline(size)

    stream = BoundedFile(payload * 10000)
    with (
        patch.object(Path, "open", return_value=stream),
        patch("scripts.lexicon_kaikki.MAX_LINE_BYTES", len(payload)),
    ):
        records = entries(tmp_path / "source")
        assert next(records)[0] == 1
        assert stream.tell() == len(payload)
        assert sum(1 for _ in records) == 9999
    stream = BoundedFile(payload * 2)
    with (
        patch.object(Path, "open", return_value=stream),
        patch("scripts.lexicon_kaikki.MAX_LINE_BYTES", len(payload) - 2),
        pytest.raises(ValueError, match="line 1: exceeds"),
    ):
        next(entries(tmp_path / "source"))


def test_enrichment_contract_and_failed_hook_are_atomic(tmp_path: Path) -> None:
    source = source_file(tmp_path, entry())
    output = tmp_path / "lexicon.sqlite"

    def enrich(db: sqlite3.Connection) -> None:
        assert db.execute("SELECT COUNT(*) FROM sense").fetchone() == (1,)
        db.execute("INSERT INTO source VALUES ('ecdict', '{}')")
        db.execute("INSERT INTO exam_tag SELECT id, 'cet4', 'ecdict' FROM lemma")
        db.execute("UPDATE sense SET gloss_zh='跑', common=1")

    build(source, output, enrichers=[enrich])
    before = output.read_bytes()
    with closing(sqlite3.connect(output)) as db:
        assert db.execute("SELECT tag FROM exam_tag").fetchone() == ("cet4",)
        assert db.execute("SELECT gloss_zh, common FROM sense").fetchone() == ("跑", 1)

    def fail(db: sqlite3.Connection) -> None:
        db.execute("UPDATE sense SET definition='not published'")
        raise RuntimeError("enrichment failed")

    with pytest.raises(RuntimeError, match="enrichment failed"):
        build(source, output, enrichers=[fail])
    assert output.read_bytes() == before
    assert not list(tmp_path.glob(".*.part*"))


def test_schema_rejects_dangling_and_invalid_relations(tmp_path: Path) -> None:
    source = source_file(tmp_path, entry())
    output = tmp_path / "lexicon.sqlite"
    build(source, output)
    with closing(sqlite3.connect(output)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        identity = db.execute("SELECT id FROM sense").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO relation VALUES (?, 'absent', 'synonym', 'wiktionary')", (identity,)
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO relation VALUES (?, ?, 'invalid', 'wiktionary')", (identity, identity)
            )


def test_cli_word_selection_and_manifest_failure(tmp_path: Path) -> None:
    source = source_file(tmp_path, entry(), entry("skip"))
    output = tmp_path / "lexicon.sqlite"
    words = tmp_path / "words.txt"
    words.write_text(" ＲＵＮ \n\n", encoding="utf-8")
    args = ["build", "--kaikki", str(source), "--output", str(output), "--words", str(words)]
    with patch("sys.argv", args):
        main()
    with closing(sqlite3.connect(output)) as db:
        assert db.execute("SELECT text FROM lemma").fetchall() == [("run",)]
    before = output.read_bytes()
    (tmp_path / "manifest.json").write_text('{"schema_version":1,"artifacts":{}}', encoding="utf-8")
    with patch("sys.argv", args), pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert output.read_bytes() == before
