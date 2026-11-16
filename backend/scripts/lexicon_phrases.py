"""Conservative source-template composition and explicitly labelled literal usage."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import structlog

from app.domain.dictionary_keys import lemma_key

from .lexicon_kaikki import entries, is_whitespace_punctuation_entry, json_text, key_text, objects

log = structlog.get_logger()
MAX_COMPONENTS = 32


def _components(template: dict[str, Any]) -> list[str] | None:
    args = template.get("args")
    if not isinstance(args, dict) or args.get("1") != "en":
        return None
    numeric = {int(key) for key, value in args.items() if key.isdecimal() and value}
    if not numeric or max(numeric) > MAX_COMPONENTS + 1:
        return None
    count = max(numeric) - 1
    if count < 2 or numeric != set(range(1, count + 2)):
        return None
    result = []
    for position in range(1, count + 1):
        word = args[str(position + 1)]
        if (
            not isinstance(word, str)
            or not word.strip()
            or any(character in word for character in "[]{}|<>")
            or args.get(f"lang{position}") not in (None, "", "en")
        ):
            return None
        result.append(key_text(lemma_key("en", word)))
    return result


def resolve_phrases(connection: sqlite3.Connection, path: Path) -> int:
    """Resolve after all English lexemes exist; never choose an ambiguous POS/etymology."""
    connection.execute(
        "CREATE TEMP TABLE phrase_candidate(phrase_id TEXT, components TEXT, "
        "PRIMARY KEY(phrase_id, components))"
    )
    skipped = 0
    for line, entry in entries(path):
        if is_whitespace_punctuation_entry(entry):
            continue
        phrase = key_text(lemma_key("en", entry["word"]))
        if (
            connection.execute(
                "SELECT 1 FROM lemma WHERE id = ? AND kind = 'phrase'", (phrase,)
            ).fetchone()
            is None
        ):
            continue
        for template in objects(entry.get("etymology_templates")):
            if template.get("name") not in {"compound", "com"}:
                continue
            components = _components(template)
            if components is None:
                skipped += 1
                log.info("phrase_mapping_skipped", line=line, reason="unsupported_template")
                # Conflicting or invalid source decompositions must not leave a partial graph.
                components = []
            connection.execute(
                "INSERT OR IGNORE INTO phrase_candidate VALUES (?, ?)",
                (phrase, json_text(components)),
            )
    for (phrase,) in connection.execute(
        "SELECT DISTINCT phrase_id FROM phrase_candidate ORDER BY phrase_id"
    ):
        candidates = connection.execute(
            "SELECT components FROM phrase_candidate WHERE phrase_id = ?", (phrase,)
        ).fetchall()
        components = json.loads(candidates[0][0])
        reason = "conflicting_templates" if len(candidates) != 1 else None
        resolved: list[str] = []
        if reason is None:
            for component in components:
                matches = connection.execute(
                    "SELECT x.id FROM lexeme x JOIN lemma l ON x.lemma_id = l.id "
                    "WHERE l.id = ? AND l.lang = 'en' AND l.kind = 'word' ORDER BY x.id",
                    (component,),
                ).fetchall()
                if len(matches) != 1:
                    reason = "missing_component" if not matches else "ambiguous_component"
                    break
                resolved.append(matches[0][0])
        if reason is not None:
            skipped += 1
            log.info("phrase_mapping_skipped", phrase=phrase, reason=reason)
            continue
        connection.executemany(
            "INSERT INTO phrase_component VALUES (?, ?, ?, 'wiktionary')",
            [(phrase, lexeme, index) for index, lexeme in enumerate(resolved)],
        )
    connection.execute("DROP TABLE phrase_candidate")
    # An example must explicitly say literal AND exactly name a known phrase containing
    # this sense's lexeme. Merely being a derived term/example is not semantic evidence.
    for sense, lexeme, examples in connection.execute("SELECT id, lexeme_id, examples FROM sense"):
        for example in json.loads(examples):
            tags = example.get("tags")
            if (
                not isinstance(tags, list)
                or "literal" not in tags
                or not isinstance(example.get("text"), str)
                or not example["text"].strip()
            ):
                continue
            phrase = key_text(lemma_key("en", example["text"]))
            if connection.execute(
                "SELECT 1 FROM phrase_component WHERE phrase_id = ? AND lexeme_id = ?",
                (phrase, lexeme),
            ).fetchone():
                connection.execute(
                    "INSERT OR IGNORE INTO phrase_usage VALUES (?, ?, 'wiktionary')",
                    (phrase, sense),
                )
    if connection.execute(
        "SELECT 1 FROM phrase_usage GROUP BY phrase_id HAVING COUNT(*) > 128 LIMIT 1"
    ).fetchone():
        raise ValueError("phrase literal usages exceed limit of 128")
    return skipped
