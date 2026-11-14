import gzip
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

# isort: split
from scripts.build_lexicon import build
from scripts.lexicon_oewn import main, oewn_enricher

FIXTURE = Path(__file__).parents[1] / "fixtures" / "oewn-small.xml"


def backbone(tmp_path: Path) -> Path:
    path = tmp_path / "kaikki.jsonl"
    words = [
        ("bright", "adj", ["intelligent", "giving much light"]),
        ("luminous", "adj", ["giving much light"]),
        ("dim", "adj", ["lacking light"]),
        ("entity", "noun", ["something with distinct existence"]),
        ("object", "noun", ["a tangible and visible entity"]),
        ("orphan", "adj", ["giving much light"]),
        ("bright", "noun", ["giving much light"]),
    ]
    path.write_text(
        "".join(
            json.dumps(
                {
                    "word": word,
                    "lang_code": "en",
                    "pos": pos,
                    "senses": [{"glosses": [gloss], "topics": ["existing"]} for gloss in glosses],
                }
            )
            + "\n"
            for word, pos, glosses in words
        ),
        encoding="utf-8",
    )
    return path


def relation_rows(db: sqlite3.Connection) -> set[tuple[str, str, str, str]]:
    return set(
        db.execute(
            "SELECT a.definition, b.definition, r.type, r.source FROM relation r "
            "JOIN sense a ON a.id=r.source_sense_id JOIN sense b ON b.id=r.target_sense_id"
        )
    )


def test_real_format_relations_direction_types_lexnames_and_idempotence(tmp_path: Path) -> None:
    output = tmp_path / "lexicon.sqlite"
    enrich = oewn_enricher(FIXTURE)
    build(backbone(tmp_path), output, enrichers=(enrich, enrich))
    with closing(sqlite3.connect(output)) as db:
        rows = relation_rows(db)
        assert rows == {
            ("giving much light", "giving much light", "synonym", "oewn"),
            ("giving much light", "lacking light", "antonym", "oewn"),
            ("lacking light", "giving much light", "antonym", "oewn"),
            (
                "a tangible and visible entity",
                "something with distinct existence",
                "hypernym",
                "oewn",
            ),
            (
                "something with distinct existence",
                "a tangible and visible entity",
                "hyponym",
                "oewn",
            ),
        }
        # Two distinct lexical senses share the same gloss; synonyms are bidirectional.
        assert db.execute("SELECT COUNT(*) FROM relation").fetchone() == (6,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute(
            "SELECT s.definition, s.lexname FROM sense s JOIN lexeme x ON x.id=s.lexeme_id "
            "JOIN lemma l ON l.id=x.lemma_id WHERE l.text='bright' ORDER BY x.pos, s.rank"
        ).fetchall() == [
            ("intelligent", None),
            ("giving much light", "adj.all"),
            ("giving much light", None),
        ]
        assert db.execute(
            "SELECT DISTINCT lexname FROM sense WHERE definition='a tangible and visible entity'"
        ).fetchall() == [("noun.Tops",)]
        assert {json.loads(row[0])[0] for row in db.execute("SELECT domain FROM sense")} == {
            "existing"
        }
        metadata = json.loads(
            db.execute("SELECT metadata FROM source WHERE name='oewn:approx'").fetchone()[0]
        )
        assert "Princeton" in metadata["attribution"]
        assert metadata["sha256"]
        assert metadata["license"] == "CC-BY-4.0 AND WordNet"


@pytest.mark.parametrize(
    ("definition", "selected", "source"),
    [
        ("giving much illumination", "giving much light", "oewn"),
        ("giving much light one two three four five six seven", "giving much light", "oewn"),
        ("giving much light one two three four five six seven eight", "intelligent", "oewn:approx"),
        ("giving blue purple yellow", "intelligent", "oewn:approx"),
        ("unrelated concept", "intelligent", "oewn:approx"),
        ("", "intelligent", "oewn:approx"),
        (None, "intelligent", "oewn:approx"),
        ("THE Giving, MUCH Light!", "giving much light", "oewn"),
    ],
)
def test_alignment_threshold_absent_gloss_and_endpoint_provenance(
    tmp_path: Path, definition: str | None, selected: str, source: str
) -> None:
    xml = FIXTURE.read_text(encoding="utf-8")
    replacement = "" if definition is None else f"<Definition>{definition}</Definition>"
    path = tmp_path / "oewn.xml"
    path.write_text(xml.replace("<Definition>giving much light</Definition>", replacement))
    output = tmp_path / "lexicon.sqlite"
    build(backbone(tmp_path), output, enrichers=(oewn_enricher(path),))
    with closing(sqlite3.connect(output)) as db:
        rows = relation_rows(db)
        assert (selected, "lacking light", "antonym", source) in rows
        assert ("lacking light", selected, "antonym", source) in rows
        assert (
            "a tangible and visible entity",
            "something with distinct existence",
            "hypernym",
            "oewn",
        ) in rows
        if source == "oewn:approx":
            assert ("intelligent", "giving much light", "synonym", source) in rows
            assert ("intelligent", "adj.all") in db.execute(
                "SELECT definition, lexname FROM sense"
            ).fetchall()


def test_gzip_and_plain_xml_produce_identical_data(tmp_path: Path) -> None:
    path = tmp_path / "english-wordnet-2025.xml.gz"
    path.write_bytes(gzip.compress(FIXTURE.read_bytes()))
    source = backbone(tmp_path)
    plain, compressed = tmp_path / "plain.sqlite", tmp_path / "compressed.sqlite"
    build(source, plain, enrichers=(oewn_enricher(FIXTURE),))
    build(source, compressed, enrichers=(oewn_enricher(path),))
    with closing(sqlite3.connect(plain)) as a, closing(sqlite3.connect(compressed)) as b:
        for table in ("relation", "sense"):
            assert (
                a.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                == b.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            )


def test_all_glosses_definitions_ties_and_existing_lexname(tmp_path: Path) -> None:
    source = backbone(tmp_path)
    entries = [json.loads(line) for line in source.read_text().splitlines()]
    # Equal maximum scores prefer the first-ranked sense, even via its secondary gloss.
    entries[0]["senses"][0]["glosses"].append("giving much light")
    source.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    path = tmp_path / "oewn.xml"
    path.write_text(
        FIXTURE.read_text().replace(
            "<Definition>giving much light</Definition>",
            "<Definition>unrelated</Definition><Definition>giving much light</Definition>",
        )
    )

    def preserve(db: sqlite3.Connection) -> None:
        db.execute("UPDATE sense SET lexname='existing.lexname' WHERE definition='intelligent'")

    output = tmp_path / "lexicon.sqlite"
    build(source, output, enrichers=(preserve, oewn_enricher(path)))
    with closing(sqlite3.connect(output)) as db:
        assert ("intelligent", "lacking light", "antonym", "oewn") in relation_rows(db)
        assert db.execute(
            "SELECT lexname FROM sense WHERE definition='intelligent'"
        ).fetchone() == ("existing.lexname",)


def test_production_wrapper_builds_with_explicit_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "lexicon.sqlite"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lexicon_oewn",
            "--kaikki",
            str(backbone(tmp_path)),
            "--oewn",
            str(FIXTURE),
            "--output",
            str(output),
        ],
    )
    main()
    with closing(sqlite3.connect(output)) as db:
        assert len(relation_rows(db)) == 5


@pytest.mark.parametrize("failure", ["xml", "gzip", "language", "empty", "manifest"])
def test_invalid_input_aborts_atomic_publication(tmp_path: Path, failure: str) -> None:
    path = tmp_path / "oewn.xml"
    xml = FIXTURE.read_text(encoding="utf-8")
    if failure == "xml":
        xml = xml[:-30]
    elif failure == "language":
        xml = xml.replace('language="en"', 'language="fr"')
    elif failure == "empty":
        xml = '<LexicalResource><Lexicon language="en"/></LexicalResource>'
    path.write_text(xml, encoding="utf-8")
    if failure == "gzip":
        path = path.with_suffix(".xml.gz")
        path.write_bytes(gzip.compress(xml.encode())[:-8])
    source = backbone(tmp_path)
    output = tmp_path / "lexicon.sqlite"
    build(source, output)
    previous = output.read_bytes()
    if failure == "manifest":
        # Keep the OEWN manifest separate from the core input's metadata.
        raw = tmp_path / "raw"
        raw.mkdir()
        path = path.rename(raw / path.name)
        (raw / "manifest.json").write_text('{"schema_version":1,"artifacts":{}}')
    with pytest.raises((ET.ParseError, EOFError, ValueError)):
        build(source, output, enrichers=(oewn_enricher(path),))
    assert output.read_bytes() == previous
    assert not list(tmp_path.glob(".*.part*"))
