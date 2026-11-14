"""Canonical wordfreq values and deterministic common-sense selection."""

import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version

import structlog

from .lexicon_kaikki import json_text

type ZipfLookup = Callable[[str], float]
log = structlog.get_logger()


def select_common(connection: sqlite3.Connection) -> None:
    """Frequency selects top senses per lexeme; primary ECDICT glosses add one."""
    connection.execute("UPDATE sense SET common = 0")
    connection.execute(
        "WITH ranked AS ("
        " SELECT s.id, l.freq_zipf, ROW_NUMBER() OVER ("
        " PARTITION BY s.lexeme_id ORDER BY s.rank, s.id) AS position"
        " FROM sense s JOIN lexeme x ON x.id = s.lexeme_id"
        " JOIN lemma l ON l.id = x.lemma_id)"
        " UPDATE sense SET common = 1 WHERE id IN ("
        " SELECT id FROM ranked WHERE position <= CASE"
        " WHEN freq_zipf >= 5 THEN 2 WHEN freq_zipf >= 3 THEN 1 ELSE 0 END)"
        " OR id IN (SELECT sense_id FROM zh_gloss"
        " WHERE source = 'ecdict' AND sense_id IS NOT NULL)"
    )


@dataclass(frozen=True)
class FrequencyResult:
    lemmas: int
    unknown: int


@dataclass
class FrequencyEnricher:
    lookup: ZipfLookup
    version: str
    result: FrequencyResult | None = None

    def __call__(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "INSERT INTO source VALUES (?, ?)",
            (
                "wordfreq",
                json_text(
                    {
                        "url": "https://github.com/rspeer/wordfreq",
                        "license": "Apache-2.0; data CC-BY-SA-4.0",
                        "license_url": "https://github.com/rspeer/wordfreq/blob/master/NOTICE.md",
                        "attribution": "Robyn Speer and wordfreq data contributors",
                        "version": self.version,
                        "language": "en",
                        "wordlist": "best",
                    }
                ),
            ),
        )
        count = unknown = 0
        for lemma_id, word in connection.execute(
            "SELECT id, text FROM lemma WHERE lang = 'en' ORDER BY id"
        ):
            value = self.lookup(word)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid wordfreq Zipf value for {word!r}: {value}")
            connection.execute(
                "INSERT INTO freq(lemma_id, zipf, source) VALUES (?, ?, ?)",
                (lemma_id, value, "wordfreq"),
            )
            connection.execute("UPDATE lemma SET freq_zipf = ? WHERE id = ?", (value, lemma_id))
            count += 1
            if value == 0:
                unknown += 1
                log.info("wordfreq_unmatched", word=word)
        select_common(connection)
        self.result = FrequencyResult(count, unknown)
        log.info("wordfreq_complete", lemmas=count, unknown=unknown)


def wordfreq_enricher(
    *, lookup: ZipfLookup | None = None, package_version: str | None = None
) -> FrequencyEnricher:
    """Create an offline hook; inject a lookup AND version for deterministic fixtures."""
    if lookup is None:
        from wordfreq import zipf_frequency

        def english_zipf(word: str) -> float:
            return zipf_frequency(word, "en", wordlist="best")

        lookup = english_zipf
        package_version = version("wordfreq")
    elif package_version is None:
        raise ValueError("an injected frequency lookup requires package_version")
    return FrequencyEnricher(lookup, package_version)
