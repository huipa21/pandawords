"""Offline SQLite builder: python -m scripts.build_lexicon [--kaikki PATH]."""

import argparse
import os
import sqlite3
from collections.abc import Callable, Iterable, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.domain.dictionary_keys import lemma_key

from .download_lexicon import checked_record, checksum, default_raw_dir, read_manifest
from .lexicon_kaikki import entries, import_entry, json_text
from .lexicon_phrases import resolve_phrases
from .lexicon_schema import initialize, validate
from .lexicon_sources import SOURCES

type Enricher = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class BuildResult:
    records: int
    skipped_senses: int
    skipped_phrase_mappings: int = 0


def build(
    kaikki: Path,
    output: Path,
    *,
    words: Set[str] | None = None,
    enrichers: Iterable[Enricher] = (),
) -> BuildResult:
    """Build, enrich and validate a private stage; only then atomically replace output.

    Enrichers run in order with the writable connection after the complete core import.
    They must not close/commit it or change the schema. Exceptions prevent publication.
    """
    if kaikki.resolve() == output.resolve():
        raise ValueError("input and output paths must differ")
    selected = None if words is None else {str(lemma_key("en", word)[1]) for word in words}
    source = SOURCES["kaikki"]
    metadata: dict[str, Any] = {
        "url": source.url,
        "license": source.license,
        "license_url": source.license_url,
        "attribution": "English Wiktionary contributors via kaikki.org / wiktextract",
        "sha256": checksum(kaikki),
    }
    manifest_path = kaikki.parent / "manifest.json"
    if manifest_path.exists():
        record = checked_record(read_manifest(manifest_path), source)
        if record is None or (
            record["filename"] != kaikki.name
            or record["sha256"] != metadata["sha256"]
            or record["bytes"] != kaikki.stat().st_size
        ):
            raise ValueError("kaikki does not match its download manifest")
        metadata["download"] = record
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name(f".{output.name}.{uuid4().hex}.part")
    records = skipped = 0
    try:
        stage.touch(exist_ok=False)
        connection = sqlite3.connect(stage)
        try:
            # Keep SQLite's cache bounded; large sort/index work may spill to disk.
            connection.execute("PRAGMA cache_size = -8192")
            connection.execute("PRAGMA temp_store = FILE")
            initialize(connection)
            connection.execute(
                "INSERT INTO source VALUES (?, ?)", ("wiktionary", json_text(metadata))
            )
            for number, entry in entries(kaikki):
                try:
                    # Check required identity even when a fixture filter excludes the word.
                    word = entry.get("word")
                    if not isinstance(word, str):
                        raise ValueError("missing word")
                    normalized = str(lemma_key("en", word)[1])
                    if selected is not None and normalized not in selected:
                        continue
                    skipped += import_entry(connection, entry)
                    records += 1
                except ValueError as error:
                    raise ValueError(f"kaikki line {number}: {error}") from error
            skipped_phrases = resolve_phrases(connection, kaikki)
            for enrich in enrichers:
                enrich(connection)
            validate(connection)
            connection.commit()
        finally:
            connection.close()
        os.replace(stage, output)
    finally:
        stage.unlink(missing_ok=True)
    return BuildResult(records, skipped, skipped_phrases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kaikki", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--words", type=Path, help="UTF-8 word list, one lemma per line")
    parser.add_argument("--ecdict", type=Path, help="Enrich with this ECDICT CSV (explicit opt-in)")
    parser.add_argument("--wordfreq", action="store_true", help="Enrich with offline wordfreq Zipf")
    parser.add_argument("--oewn", type=Path, help="Enrich with this OEWN WN-LMF XML or XML.gz")
    args = parser.parse_args()
    try:
        raw = default_raw_dir() if args.kaikki is None or args.output is None else Path()
        kaikki = args.kaikki if args.kaikki is not None else raw / SOURCES["kaikki"].filename
        output = args.output if args.output is not None else raw.parent / "lexicon.sqlite"
        words = None
        if args.words is not None:
            with args.words.open(encoding="utf-8") as file:
                words = {line.strip() for line in file if line.strip()}
        enrichers: list[Enricher] = []
        if args.ecdict is not None:
            from .lexicon_ecdict import ecdict_enricher

            enrichers.append(ecdict_enricher(args.ecdict))
        if args.wordfreq:
            from .lexicon_frequency import wordfreq_enricher

            enrichers.append(wordfreq_enricher())
        if args.oewn is not None:
            from .lexicon_oewn import oewn_enricher

            enrichers.append(oewn_enricher(args.oewn))
        result = build(kaikki, output, words=words, enrichers=enrichers)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"lexicon build failed: {error}\n")
    print(
        f"Built {output}: {result.records} records; "
        f"{result.skipped_senses} unusable senses skipped; "
        f"{result.skipped_phrase_mappings} phrase mappings skipped"
    )


if __name__ == "__main__":
    main()
