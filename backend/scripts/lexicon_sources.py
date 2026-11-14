"""Official lexicon locations and streaming, offline payload validation."""

import csv
import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


@dataclass(frozen=True)
class Source:
    name: str
    filename: str
    url: str
    license: str
    license_url: str
    version: str | None = None
    sha256: str | None = None


SOURCES = {
    "kaikki": Source(
        "kaikki",
        "kaikki-english.jsonl",
        "https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl",
        "CC-BY-SA-4.0",
        "https://en.wiktionary.org/wiki/Wiktionary:Copyrights",
    ),
    "ecdict": Source(
        "ecdict",
        "ecdict.csv",
        "https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv",
        "MIT",
        "https://github.com/skywind3000/ECDICT/blob/master/LICENSE",
    ),
    "oewn": Source(
        "oewn",
        "english-wordnet-2025.xml.gz",
        "https://github.com/globalwordnet/english-wordnet/releases/download/"
        "2025-edition/english-wordnet-2025.xml.gz",
        "CC-BY-4.0 AND WordNet",
        "https://github.com/globalwordnet/english-wordnet/blob/main/LICENSE.md",
        "2025",
        "9ca6d1dcb75f822fdd66617f7d9da48142ace38dd544d6ad5e2feca1674ad3fe",
    ),
}


def validate_payload(source: Source, path: Path) -> None:
    """Reject wrong formats and truncation without loading a dataset into RAM."""
    try:
        _validate_payload(source, path)
    except (csv.Error, ElementTree.ParseError) as error:
        raise ValueError(f"invalid {source.name} payload: {error}") from error


def _validate_payload(source: Source, path: Path) -> None:
    count = 0
    if source.name == "kaikki":
        with path.open(encoding="utf-8") as file:
            for line in file:
                entry = json.loads(line)
                if (
                    not isinstance(entry, dict)
                    or not entry.get("word")
                    or not entry.get("pos")
                    or entry.get("lang_code") != "en"
                    or not isinstance(entry.get("senses"), list)
                ):
                    raise ValueError("expected English wiktextract word/POS/senses records")
                count += 1
    elif source.name == "ecdict":
        with path.open(encoding="utf-8-sig", newline="") as file:
            rows = csv.reader(file, strict=True)
            header = next(rows, [])
            if not {"word", "translation", "pos", "tag", "exchange", "bnc", "frq"} <= set(header):
                raise ValueError("expected ECDICT CSV header")
            for row in rows:
                if not row:
                    continue
                if len(row) != len(header) or not row[header.index("word")]:
                    raise ValueError("invalid or truncated ECDICT CSV row")
                count += 1
    elif source.name == "oewn":
        lexicon = synset = False
        stack: list[ElementTree.Element] = []
        with gzip.open(path, "rb") as file:
            for event, element in ElementTree.iterparse(file, events=("start", "end")):
                if event == "start":
                    stack.append(element)
                    continue
                tag = element.tag.rsplit("}", 1)[-1]
                if tag == "Lexicon":
                    lexicon = element.get("language") == "en"
                elif tag == "Synset":
                    synset = True
                elif tag == "LexicalEntry":
                    count += 1
                stack.pop()
                if stack:
                    stack[-1].remove(element)
                element.clear()
        if not lexicon or not synset:
            raise ValueError("expected English WordNet LMF Lexicon and Synset")
    else:
        raise ValueError(f"unknown source: {source.name}")
    if count == 0:
        raise ValueError("empty dataset")
