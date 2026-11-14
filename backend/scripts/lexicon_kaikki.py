"""Streaming wiktextract transformations; memory use is bounded by one source entry."""

import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import orjson

from app.domain.dictionary_keys import DictionaryKey, lemma_key, lexeme_key, sense_key

MAX_LINE_BYTES = 16 * 1024 * 1024
REGISTERS = {"archaic", "dated", "formal", "informal", "literary", "slang", "vulgar", "obsolete"}


def json_text(value: Any) -> str:
    """Canonical JSON for structured keys and JSON-valued SQLite columns."""
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode()


def key_text(key: DictionaryKey) -> str:
    return json_text(key)


def strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def entries(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Limit individual lines as well as avoiding whole-file reads."""
    with path.open("rb") as file:
        number = 0
        while line := file.readline(MAX_LINE_BYTES + 1):
            number += 1
            if len(line) > MAX_LINE_BYTES:
                raise ValueError(f"kaikki line {number}: exceeds {MAX_LINE_BYTES} bytes")
            try:
                entry = orjson.loads(line)
            except orjson.JSONDecodeError as error:
                raise ValueError(f"kaikki line {number}: invalid JSON") from error
            if not isinstance(entry, dict):
                raise ValueError(f"kaikki line {number}: expected an object")
            yield number, entry


def add_lemma(connection: sqlite3.Connection, word: str) -> str:
    key = lemma_key("en", word)
    identity = key_text(key)
    text = str(key[1])
    connection.execute(
        "INSERT OR IGNORE INTO lemma(id, text, lang, kind, source) VALUES (?, ?, 'en', ?, ?)",
        (identity, text, "phrase" if " " in text else "word", "wiktionary"),
    )
    connection.execute("INSERT OR IGNORE INTO form_index VALUES (?, ?)", (text, identity))
    return identity


def add_senses(connection: sqlite3.Connection, entry: dict[str, Any], lexeme_id: str) -> int:
    skipped = 0
    for rank, sense in enumerate(entry["senses"], 1):
        if not isinstance(sense, dict):
            skipped += 1
            continue
        glosses = strings(sense.get("glosses")) or strings(sense.get("raw_glosses"))
        if not glosses:
            skipped += 1
            continue
        source_id = sense.get("id")
        if not isinstance(source_id, str) or not source_id.strip():
            source_id = None
        identity = sense_key(
            "en",
            entry["word"],
            entry["pos"],
            entry.get("etymology_number") or 1,
            source_sense_id=source_id,
            gloss=glosses[0],
        )
        tags = strings(sense.get("tags"))
        connection.execute(
            """INSERT OR IGNORE INTO sense
            (id, lexeme_id, definition, glosses, tags, register, domain, examples,
             rank, source, source_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                key_text(identity),
                lexeme_id,
                glosses[0],
                json_text(glosses),
                json_text(tags),
                json_text([tag for tag in tags if tag in REGISTERS]),
                json_text(strings(sense.get("topics"))),
                json_text(objects(sense.get("examples"))),
                rank,
                "wiktionary",
                source_id,
            ),
        )
        for target in objects(sense.get("form_of")):
            word = target.get("word")
            if isinstance(word, str) and word.strip():
                target_id = add_lemma(connection, word)
                normalized = str(lemma_key("en", entry["word"])[1])
                connection.execute(
                    "INSERT OR IGNORE INTO form_index VALUES (?, ?)", (normalized, target_id)
                )
    return skipped


def add_sounds(connection: sqlite3.Connection, entry: dict[str, Any], lexeme_id: str) -> None:
    for sound in objects(entry.get("sounds")):
        ipa = sound.get("ipa")
        if not isinstance(ipa, str) or not ipa.strip():
            ipa = None
        # Retain media attribution and future upstream audio fields without fetching media.
        audio = {key: value for key, value in sound.items() if key not in {"ipa", "tags"}}
        if ipa is None and not any(sound.get(key) for key in ("audio", "ogg_url", "mp3_url")):
            continue
        tags = strings(sound.get("tags"))
        accents: list[str | None] = []
        if set(tags) & {"US", "General-American"}:
            accents.append("US")
        if set(tags) & {"UK", "Received-Pronunciation"}:
            accents.append("UK")
        for accent in accents or [None]:
            identity = hashlib.sha256(json_text([lexeme_id, accent, sound]).encode()).hexdigest()
            connection.execute(
                "INSERT OR IGNORE INTO pron VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identity, lexeme_id, accent, ipa, json_text(audio), json_text(tags), "wiktionary"),
            )


def import_entry(connection: sqlite3.Connection, entry: dict[str, Any]) -> int:
    """Import one English entry; return the number of skipped unusable senses."""
    if entry.get("lang_code") != "en" or not isinstance(entry.get("senses"), list):
        raise ValueError("expected English word/POS/senses record")
    word, pos = entry.get("word"), entry.get("pos")
    if not isinstance(word, str) or not isinstance(pos, str):
        raise ValueError("word and POS must be nonblank strings")
    etymology = entry.get("etymology_number", 1)
    if etymology is None:
        etymology = 1
    key = lexeme_key("en", word, pos, etymology)
    lemma_id = add_lemma(connection, word)
    lexeme_id = key_text(key)
    etymology_text = entry.get("etymology_text")
    connection.execute(
        "INSERT OR IGNORE INTO lexeme VALUES (?, ?, ?, ?, ?, ?)",
        (
            lexeme_id,
            lemma_id,
            key[2],
            key[3],
            etymology_text if isinstance(etymology_text, str) else None,
            "wiktionary",
        ),
    )
    skipped = add_senses(connection, entry, lexeme_id)
    add_sounds(connection, entry, lexeme_id)
    for form in objects(entry.get("forms")):
        text = form.get("form")
        if not isinstance(text, str) or not text.strip():
            continue
        normalized = str(lemma_key("en", text)[1])
        connection.execute(
            "INSERT OR IGNORE INTO form VALUES (?, ?, ?, ?)",
            (lexeme_id, text, json_text(strings(form.get("tags"))), "wiktionary"),
        )
        connection.execute("INSERT OR IGNORE INTO form_index VALUES (?, ?)", (normalized, lemma_id))
    return skipped
