"""Offline OEWN enrichment hook and standalone production build wrapper."""

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.dictionary_keys import lemma_key

from .download_lexicon import checked_record, checksum, read_manifest
from .lexicon_kaikki import key_text
from .lexicon_oewn_xml import records
from .lexicon_sources import SOURCES

GLOSS_THRESHOLD = 0.3
POS = {"n": "noun", "v": "verb", "a": "adj", "s": "adj", "r": "adv"}
RELATIONS = frozenset({"synonym", "antonym", "hypernym", "hyponym"})
STOPWORDS = frozenset("a an the to of and or in on at for by with be is are that which".split())


@dataclass(frozen=True)
class Alignment:
    sense: str
    approximate: bool


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())) - STOPWORDS


def _candidates(db: sqlite3.Connection, lemma: str, pos: str) -> list[tuple[str, str]]:
    return db.execute(
        "SELECT s.id, s.glosses FROM sense s JOIN lexeme x ON x.id=s.lexeme_id "
        "WHERE x.lemma_id=? AND x.pos=? ORDER BY x.etymology_no, s.rank, s.id",
        (lemma, pos),
    ).fetchall()


def _align(candidates: list[tuple[str, str]], definitions: list[str]) -> Alignment:
    definitions_tokens = [_tokens(definition) for definition in definitions]
    best_id, best_score = candidates[0][0], 0.0
    for sense_id, glosses in candidates:
        for gloss in json.loads(glosses):
            tokens = _tokens(gloss)
            for other in definitions_tokens:
                union = tokens | other
                score = len(tokens & other) / len(union) if union else 0.0
                if score > best_score:
                    best_id, best_score = sense_id, score
    if best_score >= GLOSS_THRESHOLD:
        return Alignment(best_id, False)
    return Alignment(candidates[0][0], True)


def _metadata(path: Path) -> dict[str, Any]:
    source = SOURCES["oewn"]
    metadata: dict[str, Any] = {
        "url": source.url,
        "license": source.license,
        "license_url": source.license_url,
        "version": source.version,
        "attribution": "Open English WordNet team and Princeton WordNet team",
        "sha256": checksum(path),
        "alignment": {
            "metric": "maximum pairwise gloss token Jaccard",
            "threshold": GLOSS_THRESHOLD,
            "stopwords": sorted(STOPWORDS),
            "fallback": "first etymology, then top-ranked sense",
        },
    }
    manifest = path.parent / "manifest.json"
    if manifest.exists():
        record = checked_record(read_manifest(manifest), source)
        if record is None or (
            record["filename"] != path.name
            or record["sha256"] != metadata["sha256"]
            or record["bytes"] != path.stat().st_size
        ):
            raise ValueError("oewn does not match its download manifest")
        metadata["download"] = record
    return metadata


def oewn_enricher(path: Path) -> Callable[[sqlite3.Connection], None]:
    """Bind plain/gzipped WN-LMF input; do not commit, close, or change the caller's schema."""

    def enrich(db: sqlite3.Connection) -> None:
        metadata = _metadata(path)
        for source in ("oewn", "oewn:approx"):
            db.execute(
                "INSERT INTO source(name, metadata) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET metadata=excluded.metadata",
                (source, json.dumps(metadata)),
            )
        _import(db, path)

    return enrich


def _import(db: sqlite3.Connection, path: Path) -> None:
    pending: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    # Entries precede synsets in WN-LMF. Retain only identities present in the backbone.
    for entry in records(path):
        if entry.tag != "LexicalEntry":
            continue
        lemma = entry.find("Lemma")
        if lemma is None:
            continue
        word, pos = lemma.get("writtenForm", ""), POS.get(lemma.get("partOfSpeech", ""))
        if not word.strip() or pos is None:
            continue
        lemma_id = key_text(lemma_key("en", word))
        if not _candidates(db, lemma_id, pos):
            continue
        for sense in entry.findall("Sense"):
            sense_id, synset = sense.get("id"), sense.get("synset")
            if sense_id and synset:
                pending[synset].append((sense_id, lemma_id, pos))

    senses: dict[str, Alignment] = {}
    synsets: dict[str, list[Alignment]] = {}
    for synset in records(path):
        if synset.tag != "Synset":
            continue
        synset_id = synset.get("id", "")
        definitions = ["".join(node.itertext()) for node in synset.findall("Definition")]
        members: list[Alignment] = []
        for sense_id, lemma_id, pos in pending.pop(synset_id, []):
            alignment = _align(_candidates(db, lemma_id, pos), definitions)
            senses[sense_id] = alignment
            members.append(alignment)
            lexname = synset.get("lexfile")
            if lexname:
                db.execute(
                    "UPDATE sense SET lexname=? WHERE id=? AND lexname IS NULL",
                    (lexname, alignment.sense),
                )
        if members:
            synsets[synset_id] = members
    del pending

    for members in synsets.values():
        for source in members:
            _emit(db, [source], members, "synonym")
    # Re-read instead of keeping the full source relation graph in memory.
    for record in records(path):
        if record.tag == "LexicalEntry":
            for sense in record.findall("Sense"):
                aligned = senses.get(sense.get("id", ""))
                if aligned is None:
                    continue
                for relation in sense.findall("SenseRelation"):
                    target = senses.get(relation.get("target", ""))
                    if target is not None:
                        _emit(db, [aligned], [target], relation.get("relType", ""))
        elif record.tag == "Synset":
            for relation in record.findall("SynsetRelation"):
                _emit(
                    db,
                    synsets.get(record.get("id", ""), []),
                    synsets.get(relation.get("target", ""), []),
                    relation.get("relType", ""),
                )


def _emit(
    db: sqlite3.Connection,
    sources: Iterable[Alignment],
    targets: list[Alignment],
    relation: str,
) -> None:
    if relation not in RELATIONS:
        return
    for source in sources:
        for target in targets:
            if source.sense != target.sense:
                db.execute(
                    "INSERT OR IGNORE INTO relation VALUES (?, ?, ?, ?)",
                    (
                        source.sense,
                        target.sense,
                        relation,
                        "oewn:approx" if source.approximate or target.approximate else "oewn",
                    ),
                )


def main() -> None:
    """Build from explicit inputs without changing the core CLI or shared defaults."""
    from .build_lexicon import build

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kaikki", required=True, type=Path)
    parser.add_argument("--oewn", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.oewn.resolve() == args.output.resolve():
        parser.error("OEWN input and output paths must differ")
    build(args.kaikki, args.output, enrichers=(oewn_enricher(args.oewn),))


if __name__ == "__main__":
    main()
