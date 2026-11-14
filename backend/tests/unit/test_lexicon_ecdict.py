import csv
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

# isort: split
from scripts.build_lexicon import build, main
from scripts.lexicon_ecdict import ecdict_enricher
from scripts.lexicon_frequency import wordfreq_enricher


def sources(tmp_path: Path) -> tuple[Path, Path]:
    kaikki = tmp_path / "kaikki.jsonl"
    records = [
        {
            "word": word,
            "lang_code": "en",
            "pos": pos,
            "etymology_number": etymology,
            "senses": [{"glosses": [f"{word} sense {i}"]} for i in range(1, 4)],
        }
        for word, pos, etymology in [
            ("run", "verb", 1),
            ("run", "noun", 1),
            ("bank", "noun", 1),
            ("bank", "noun", 2),
            ("high", "adj", 1),
            ("mid", "adj", 1),
            ("low", "adj", 1),
            ("unknown", "noun", 1),
            ("solo", "noun", 1),
        ]
    ]
    kaikki.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    ecdict = tmp_path / "ecdict.csv"
    with ecdict.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "word",
                "translation",
                "pos",
                "tag",
                "exchange",
                "bnc",
                "frq",
            ],
        )
        writer.writeheader()
        for word, translation, tags, bnc in [
            ("ＲＵＮ", r"v. 跑; 跑; 运行\nn. 跑步", "cet4 cet4 gre unknown zk", "12"),
            ("run", "v. 冲突", "ielts", "99"),
            ("bank", "n. 银行", "cet6", "0"),
            ("absent", "n. 不存在", "", ""),
            ("solo", "独自", "gk ky toefl ielts", "0"),
            ("unknown", "xyz. 未知", "", ""),
        ]:
            writer.writerow(
                dict(
                    word=word,
                    translation=translation,
                    pos="",
                    tag=tags,
                    exchange="",
                    bnc=bnc,
                    frq="0",
                )
            )
    return kaikki, ecdict


def frequency(word: str) -> float:
    return {"high": 5.0, "mid": 3.0, "low": 2.99, "run": 1.5}.get(word, 0.0)


def test_enrichment_matching_duplicates_attribution_and_rebuild(tmp_path: Path) -> None:
    kaikki, csv_path = sources(tmp_path)
    dumps: list[list[str]] = []
    for name in ("first", "second"):
        ecdict = ecdict_enricher(csv_path)
        freq = wordfreq_enricher(lookup=frequency, package_version="fixture-v1")
        output = tmp_path / f"{name}.sqlite"
        build(kaikki, output, enrichers=(ecdict, freq))
        assert ecdict.result is not None
        assert (ecdict.result.rows, ecdict.result.matched, ecdict.result.unmatched) == (6, 5, 1)
        assert (ecdict.result.duplicates, ecdict.result.ambiguous) == (1, 1)
        assert (ecdict.result.glosses, ecdict.result.unmatched_glosses) == (4, 1)
        assert freq.result is not None
        assert (freq.result.lemmas, freq.result.unknown) == (7, 3)
        with closing(sqlite3.connect(output)) as db:
            dumps.append(list(db.iterdump()))
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
            assert db.execute("SELECT gloss FROM zh_gloss ORDER BY gloss").fetchall() == [
                ("独自",),
                ("跑",),
                ("跑步",),
                ("运行",),
            ]
            assert db.execute(
                "SELECT count(*) FROM zh_gloss WHERE sense_id IS NOT NULL"
            ).fetchone() == (3,)
            assert {row[0] for row in db.execute("SELECT tag FROM exam_tag")} == {
                "zk",
                "cet4",
                "cet6",
                "gre",
                "gk",
                "ky",
                "toefl",
                "ielts",
            }
            assert db.execute(
                "SELECT bnc, coca, zipf FROM freq JOIN lemma ON lemma.id = freq.lemma_id "
                "WHERE lemma.text = 'run' AND freq.source = 'ecdict'"
            ).fetchone() == (12, None, None)
            assert db.execute(
                "SELECT lemma.freq_zipf, freq.zipf FROM lemma "
                "JOIN freq ON lemma.id = freq.lemma_id "
                "WHERE lemma.text = 'run' AND freq.source = 'wordfreq'"
            ).fetchone() == (1.5, 1.5)
            metadata = {
                key: json.loads(value)
                for key, value in db.execute("SELECT name, metadata FROM source")
            }
            assert metadata["ecdict"]["license"] == "MIT"
            assert len(metadata["ecdict"]["sha256"]) == 64
            assert metadata["wordfreq"]["version"] == "fixture-v1"
            assert "CC-BY-SA" in metadata["wordfreq"]["license"]
    assert dumps[0] == dumps[1]


@pytest.mark.parametrize("reverse", [False, True])
def test_common_frequency_boundaries_primary_gloss_and_hook_order(
    tmp_path: Path, reverse: bool
) -> None:
    kaikki, csv_path = sources(tmp_path)
    hooks = [
        ecdict_enricher(csv_path),
        wordfreq_enricher(lookup=frequency, package_version="fixture-v1"),
    ]
    output = tmp_path / "common.sqlite"
    build(kaikki, output, enrichers=reversed(hooks) if reverse else hooks)
    with closing(sqlite3.connect(output)) as db:
        actual = db.execute(
            "SELECT l.text, x.pos, x.etymology_no, sum(s.common) FROM sense s "
            "JOIN lexeme x ON x.id = s.lexeme_id JOIN lemma l ON l.id = x.lemma_id "
            "GROUP BY x.id ORDER BY l.text, x.pos, x.etymology_no"
        ).fetchall()
        assert actual == [
            ("bank", "noun", 1, 0),
            ("bank", "noun", 2, 0),
            ("high", "adj", 1, 2),
            ("low", "adj", 1, 0),
            ("mid", "adj", 1, 1),
            ("run", "noun", 1, 1),
            ("run", "verb", 1, 1),
            ("solo", "noun", 1, 1),
            ("unknown", "noun", 1, 0),
        ]


def test_unlabeled_polysemy_is_not_guessed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kaikki, csv_path = sources(tmp_path)
    csv_path.write_text(
        "word,translation,pos,tag,exchange,bnc,frq\nrun,跑,,,,0,0\n",
        encoding="utf-8",
    )
    hook = ecdict_enricher(csv_path)
    build(kaikki, tmp_path / "ambiguous.sqlite", enrichers=(hook,))
    assert hook.result is not None and hook.result.ambiguous == 1
    assert hook.result.glosses == 0
    assert "ambiguous_lexeme" in capsys.readouterr().out


def test_missing_invalid_sources_and_invalid_zipf_preserve_output(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="requested ECDICT source"):
        ecdict_enricher(tmp_path / "missing.csv")
    kaikki, csv_path = sources(tmp_path)
    output = tmp_path / "existing.sqlite"
    output.write_bytes(b"previous")
    for value in (float("nan"), -1.0, float("inf")):
        hook = wordfreq_enricher(lookup=lambda _, value=value: value, package_version="bad")
        with pytest.raises(ValueError, match="invalid wordfreq Zipf"):
            build(kaikki, output, enrichers=(hook,))
        assert output.read_bytes() == b"previous"
    csv_path.write_text("word,translation\nrun,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ECDICT CSV header"):
        build(kaikki, output, enrichers=(ecdict_enricher(csv_path),))
    assert output.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".*.part"))


def test_cli_enrichment_opt_in_and_real_wordfreq(tmp_path: Path) -> None:
    kaikki, csv_path = sources(tmp_path)
    output = tmp_path / "cli.sqlite"
    with patch(
        "sys.argv",
        [
            "build_lexicon",
            "--kaikki",
            str(kaikki),
            "--output",
            str(output),
            "--ecdict",
            str(csv_path),
            "--wordfreq",
        ],
    ):
        main()
    with closing(sqlite3.connect(output)) as db:
        assert db.execute("SELECT freq_zipf FROM lemma WHERE text = 'run'").fetchone()[0] > 3
        assert db.execute("SELECT count(*) FROM zh_gloss").fetchone() == (4,)
