import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

# isort: split
from scripts.build_lexicon import build


def template(root: str = "decide", suffix: str = "ion", **arguments: Any) -> dict[str, Any]:
    return {"name": "suffix", "args": {"1": "en", "2": root, "3": suffix, **arguments}}


def build_components(tmp_path: Path, *templates: Any) -> list[tuple[int, str, str]]:
    source = tmp_path / "kaikki.jsonl"
    source.write_text(
        json.dumps(
            {
                "word": "decision",
                "lang_code": "en",
                "pos": "noun",
                "senses": [{"glosses": ["A choice made after thinking."]}],
                "etymology_templates": list(templates),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "lexicon.sqlite"
    build(source, output)
    with closing(sqlite3.connect(output)) as connection:
        return connection.execute(
            "SELECT position, text, type FROM affix ORDER BY position"
        ).fetchall()


@pytest.mark.parametrize("name", ["suffix", "suf"])
def test_suffix_templates_normalize_base_and_suffix(tmp_path: Path, name: str) -> None:
    record = {**template("  ＤＥＣＩＤＥ ", "-ION", alt1="decis"), "name": name}
    assert build_components(tmp_path, record, record) == [
        (0, "decide", "root"),
        (1, "-ion", "suffix"),
    ]


@pytest.mark.parametrize(
    "records",
    [
        [None, {"name": "suffix", "args": None}],
        [{"name": [], "args": {}}],
        [{"name": "unknown", "args": {"1": "en", "2": "decide", "3": "ion"}}],
        [template("", "ion")],
        [template("-", "ion")],
        [template("decide", "-")],
        [template("[[decide]]")],
        [template(**{"1": "fr"})],
        [template(lang1="fr")],
        [template(lang2="fr")],
        [template(lang1=[])],
        [template(**{"4": "extra"})],
        [template(), template("another-base")],
    ],
)
def test_unsupported_or_ambiguous_templates_are_not_guessed(
    tmp_path: Path, records: list[Any]
) -> None:
    assert build_components(tmp_path, *records) == []


def test_duplicate_backbone_records_reject_conflicting_analyses(tmp_path: Path) -> None:
    build_components(tmp_path, template())
    source = tmp_path / "kaikki.jsonl"
    first = source.read_text(encoding="utf-8")
    duplicate = json.loads(first)
    duplicate["etymology_templates"] = [template("another-base", "s")]
    source.write_text(first + json.dumps(duplicate) + "\n", encoding="utf-8")
    output = tmp_path / "lexicon.sqlite"
    build(source, output)
    with closing(sqlite3.connect(output)) as connection:
        assert (
            connection.execute(
                "SELECT position, text, type FROM affix ORDER BY position"
            ).fetchall()
            == []
        )
        assert connection.execute("SELECT status, reason FROM morphology_analysis").fetchone() == (
            "rejected",
            "conflicting_records",
        )


@pytest.mark.parametrize(
    ("name", "parts", "expected"),
    [
        ("prefix", ["re", "decide"], [(0, "re-", "prefix"), (1, "decide", "root")]),
        ("pre", ["re-", "decide"], [(0, "re-", "prefix"), (1, "decide", "root")]),
        (
            "affix",
            ["re-", "decide", "-ion"],
            [(0, "re-", "prefix"), (1, "decide", "root"), (2, "-ion", "suffix")],
        ),
        (
            "af",
            ["root", "-in-", "root"],
            [(0, "root", "root"), (1, "-in-", "infix"), (2, "root", "root")],
        ),
        ("compound", ["echo", "echo"], [(0, "echo", "root"), (1, "echo", "root")]),
    ],
)
def test_source_types_order_and_repeated_components(
    tmp_path: Path, name: str, parts: list[str], expected: list[tuple[int, str, str]]
) -> None:
    record = {
        "name": name,
        "args": {"1": "en", **{str(index + 2): part for index, part in enumerate(parts)}},
    }
    assert build_components(tmp_path, record) == expected


def test_invalid_template_alongside_valid_is_not_silently_discarded(tmp_path: Path) -> None:
    assert build_components(tmp_path, template(), template("", "ion")) == []
    with closing(sqlite3.connect(tmp_path / "lexicon.sqlite")) as connection:
        assert connection.execute("SELECT status, reason FROM morphology_analysis").fetchone() == (
            "rejected",
            "malformed_order",
        )
