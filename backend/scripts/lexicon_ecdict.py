"""Streaming ECDICT Chinese glosses, exam tags and source frequency ranks."""

import csv
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import structlog

from app.domain.dictionary_keys import lemma_key

from .download_lexicon import checked_record, checksum, read_manifest
from .lexicon_frequency import select_common
from .lexicon_kaikki import json_text, key_text
from .lexicon_sources import SOURCES, validate_payload

log = structlog.get_logger()
EXAMS = frozenset("zk gk cet4 cet6 ky toefl ielts gre".split())
POS = {
    "n": "noun",
    "v": "verb",
    "vt": "verb",
    "vi": "verb",
    "a": "adj",
    "adj": "adj",
    "ad": "adv",
    "adv": "adv",
    "pron": "pron",
    "prep": "prep",
    "conj": "conj",
    "interj": "intj",
    "int": "intj",
    "num": "num",
    "art": "article",
    "aux": "verb",
}
LABEL = re.compile(r"^([A-Za-z]+(?:\s*[/&]\s*[A-Za-z]+)*)\.\s*(.*)$")


@dataclass
class EcdictResult:
    rows: int = 0
    matched: int = 0
    unmatched: int = 0
    unmatched_glosses: int = 0
    ambiguous: int = 0
    duplicates: int = 0
    glosses: int = 0


def _rank(value: str, line: int) -> int | None:
    if not value.strip() or value.strip() == "0":
        return None
    if not value.strip().isdigit() or int(value) < 1:
        raise ValueError(f"ecdict line {line}: invalid frequency rank {value!r}")
    return int(value)


def _glosses(translation: str) -> list[tuple[str | None, str]]:
    result: list[tuple[str | None, str]] = []
    current: tuple[str | None, ...] = (None,)
    for text in translation.replace("\\n", "\n").splitlines():
        text = text.strip()
        if not text:
            continue
        match = LABEL.match(text)
        if match:
            labels, text = match.groups()
            current = tuple(
                sorted(
                    {
                        POS.get(label.strip().lower(), "unsupported")
                        for label in re.split(r"[/&]", labels)
                    }
                )
            )
        for gloss in re.split("[;；]", text):
            gloss = gloss.strip()
            for pos in current:
                pair = (pos, gloss)
                if gloss and pair not in result:
                    result.append(pair)
    return result


@dataclass
class EcdictEnricher:
    path: Path
    result: EcdictResult | None = None

    def __call__(self, connection: sqlite3.Connection) -> None:
        validate_payload(SOURCES["ecdict"], self.path)
        source = SOURCES["ecdict"]
        metadata: dict[str, Any] = {
            "url": source.url,
            "license": source.license,
            "license_url": source.license_url,
            "attribution": "skywind3000 and ECDICT contributors",
            "sha256": checksum(self.path),
        }
        manifest_path = self.path.parent / "manifest.json"
        if manifest_path.exists():
            record = checked_record(read_manifest(manifest_path), source)
            if record is None or (
                record["filename"] != self.path.name
                or record["sha256"] != metadata["sha256"]
                or record["bytes"] != self.path.stat().st_size
            ):
                raise ValueError("ecdict does not match its download manifest")
            metadata["download"] = record
        connection.execute("INSERT INTO source VALUES (?, ?)", ("ecdict", json_text(metadata)))
        result = EcdictResult()
        with self.path.open(encoding="utf-8-sig", newline="") as file:
            for line, row in enumerate(csv.DictReader(file, strict=True), 2):
                result.rows += 1
                self._row(connection, row, line, result)
        select_common(connection)
        self.result = result
        log.info("ecdict_complete", **asdict(result))

    def _row(
        self, db: sqlite3.Connection, row: dict[str, str], line: int, result: EcdictResult
    ) -> None:
        lemma_id = key_text(lemma_key("en", row["word"]))
        bnc, coca = _rank(row["bnc"], line), _rank(row["frq"], line)
        if db.execute("SELECT 1 FROM lemma WHERE id = ?", (lemma_id,)).fetchone() is None:
            result.unmatched += 1
            log.info("ecdict_unmatched", line=line, word=row["word"], reason="lemma_absent")
            return
        result.matched += 1
        inserted = db.execute(
            "INSERT OR IGNORE INTO freq(lemma_id, bnc, coca, source) VALUES (?, ?, ?, ?)",
            (lemma_id, bnc, coca, "ecdict"),
        ).rowcount
        if not inserted:
            result.duplicates += 1
            log.info("ecdict_duplicate", line=line, word=row["word"], policy="first_row_wins")
            return
        for tag in sorted(set(row["tag"].lower().split()) & EXAMS):
            db.execute("INSERT INTO exam_tag VALUES (?, ?, ?)", (lemma_id, tag, "ecdict"))
        lexemes = db.execute(
            "SELECT id, pos FROM lexeme WHERE lemma_id = ? ORDER BY id", (lemma_id,)
        ).fetchall()
        for pos, gloss in _glosses(row["translation"]):
            candidates = [key for key, part in lexemes if pos is None or part == pos]
            if len(candidates) != 1:
                result.ambiguous += len(candidates) > 1
                result.unmatched_glosses += not candidates
                log.info(
                    "ecdict_gloss_unresolved",
                    line=line,
                    word=row["word"],
                    pos=pos,
                    reason="ambiguous_lexeme" if candidates else "pos_absent",
                    candidates=len(candidates),
                )
                continue
            lexeme_id = candidates[0]
            top = db.execute(
                "SELECT id, gloss_zh FROM sense WHERE lexeme_id = ? ORDER BY rank, id LIMIT 1",
                (lexeme_id,),
            ).fetchone()
            sense_id = None
            if top is not None and top[1] is None:
                sense_id = top[0]
                db.execute("UPDATE sense SET gloss_zh = ? WHERE id = ?", (gloss, top[0]))
            result.glosses += db.execute(
                "INSERT OR IGNORE INTO zh_gloss VALUES (?, ?, ?, ?)",
                (lexeme_id, gloss, "ecdict", sense_id),
            ).rowcount


def ecdict_enricher(path: Path) -> EcdictEnricher:
    """Create a typed builder hook. Missing requested sources fail, never silently skip."""
    if not path.is_file():
        raise FileNotFoundError(f"requested ECDICT source is missing: {path}")
    return EcdictEnricher(path)
