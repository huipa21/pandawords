"""Conservative source-template analyses; never segment a word's spelling."""

import sqlite3
from typing import Any

from app.domain.dictionary_keys import lemma_key
from app.domain.morphology import component_order_valid

from .lexicon_kaikki import json_text

NAMES = {
    "suffix": "suffix",
    "suf": "suffix",
    "prefix": "prefix",
    "pre": "prefix",
    "affix": "affix",
    "af": "affix",
    "compound": "compound",
    "com": "compound",
}


def _component(value: Any, kind: str | None) -> tuple[str, str]:
    if not isinstance(value, str) or any(c in value for c in "[]{}|<>/"):
        raise ValueError("malformed_component")
    text = str(lemma_key("en", value)[1])
    if kind is None:
        kind = (
            "infix"
            if text.startswith("-") and text.endswith("-")
            else "suffix"
            if text.startswith("-")
            else "prefix"
            if text.endswith("-")
            else "root"
        )
    bare = text.strip("-")
    if not bare or " " in bare or (kind == "root" and bare != text):
        raise ValueError("malformed_component")
    text = {"prefix": bare + "-", "suffix": "-" + bare, "infix": "-" + bare + "-"}.get(kind, bare)
    return text, kind


def parse(templates: Any) -> tuple[list[tuple[str, str]], str, str]:
    if templates is None or templates == []:
        return [], "absent", "no_templates"
    if not isinstance(templates, list):
        return [], "rejected", "malformed_templates"
    candidates: set[tuple[tuple[str, str], ...]] = set()
    for template in templates:
        if not isinstance(template, dict) or not isinstance(template.get("name"), str):
            return [], "rejected", "malformed_template"
        name = NAMES.get(template["name"])
        if name is None:
            return [], "rejected", "unsupported_template"
        args = template.get("args")
        if not isinstance(args, dict) or args.get("1") != "en":
            return [], "rejected", "unsupported_language"
        if any(
            key.startswith("lang") and value not in (None, "", "en") for key, value in args.items()
        ):
            return [], "rejected", "unsupported_language"
        numbered = {
            int(key): value
            for key, value in args.items()
            if key.isdecimal() and int(key) > 1 and value not in (None, "")
        }
        if (
            not 2 <= len(numbered) <= 16
            or sorted(numbered) != list(range(2, len(numbered) + 2))
            or (name in {"prefix", "suffix"} and len(numbered) != 2)
        ):
            return [], "rejected", "malformed_order"
        kinds: list[str | None] = (
            ["prefix", "root"]
            if name == "prefix"
            else ["root", "suffix"]
            if name == "suffix"
            else ["root"] * len(numbered)
            if name == "compound"
            else [None] * len(numbered)
        )
        try:
            parts = tuple(_component(numbered[index + 2], kind) for index, kind in enumerate(kinds))
        except ValueError:
            return [], "rejected", "malformed_component"
        if not any(kind == "root" for _, kind in parts):
            return [], "rejected", "missing_root"
        if not component_order_valid([kind for _, kind in parts]):
            return [], "rejected", "malformed_type_order"
        candidates.add(parts)
    if len(candidates) != 1:
        return [], "rejected", "conflicting_templates"
    return list(candidates.pop()), "supported", "validated_templates"


def add_analysis(connection: sqlite3.Connection, entry: dict[str, Any], lexeme: str) -> None:
    parts, status, reason = parse(entry.get("etymology_templates"))
    canonical = json_text(parts)
    previous = connection.execute(
        "SELECT status, components FROM morphology_analysis WHERE lexeme_id = ?", (lexeme,)
    ).fetchone()
    if previous is not None and previous != (status, canonical):
        status, reason, parts, canonical = "rejected", "conflicting_records", [], "[]"
    connection.execute(
        "INSERT INTO morphology_analysis VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(lexeme_id) DO UPDATE SET status=excluded.status, reason=excluded.reason, "
        "components=excluded.components",
        (lexeme, status, reason, canonical, "wiktionary"),
    )
    connection.execute("DELETE FROM affix WHERE lexeme_id = ?", (lexeme,))
    connection.executemany(
        "INSERT INTO affix VALUES (?, ?, ?, ?, 'wiktionary')",
        [(lexeme, index, text, kind) for index, (text, kind) in enumerate(parts)],
    )
