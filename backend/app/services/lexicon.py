"""Asynchronous, read-only access to the versioned offline lexicon artifact."""

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.errors import AppError
from app.domain.dictionary_keys import DictionaryKey, lemma_key
from app.domain.lexicon import (
    Accent,
    LexiconAffix,
    LexiconForm,
    LexiconFrequency,
    LexiconGloss,
    LexiconLemma,
    LexiconLexeme,
    LexiconPronunciation,
    LexiconRecord,
    LexiconRelation,
    LexiconSense,
    LexiconSource,
    LexiconTag,
    RelationDirection,
    RelationType,
)

_TABLES: dict[str, type[LexiconRecord]] = {
    "lemma": LexiconLemma,
    "lexeme": LexiconLexeme,
    "sense": LexiconSense,
    "pron": LexiconPronunciation,
    "form": LexiconForm,
    "relation": LexiconRelation,
    "zh_gloss": LexiconGloss,
    "exam_tag": LexiconTag,
    "freq": LexiconFrequency,
    "affix": LexiconAffix,
    "source": LexiconSource,
}
_JSON_COLUMNS = {
    "glosses",
    "tags",
    "register",
    "domain",
    "examples",
    "audio",
    "metadata",
}
_KEY_COLUMNS = {"lemma_id", "lexeme_id", "sense_id", "source_sense_id", "target_sense_id"}


def _key(value: DictionaryKey) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class LexiconReader:
    """No connection escapes a read; safe across tasks and file replacement on Windows.

    Construct with an explicit configured path. Call validate() at startup for eager errors.
    All I/O runs in worker threads, using a fresh read-only connection for each operation.
    Missing records return None / []; invalid artifacts raise AppError (503).
    """

    def __init__(self, path: Path) -> None:
        self._path = path.resolve()

    def _connect(self) -> sqlite3.Connection:
        if not self._path.exists():
            raise AppError("lexicon.missing", 503, f"Lexicon database is missing: {self._path}")
        connection = sqlite3.connect(f"{self._path.as_uri()}?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only = ON")
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("unsupported schema version (expected 1)")
        except Exception:
            connection.close()
            raise
        connection.row_factory = sqlite3.Row
        return connection

    def _invalid(self, error: Exception) -> AppError:
        return AppError("lexicon.invalid", 503, f"Invalid lexicon database: {self._path}: {error}")

    def _validate(self) -> None:
        try:
            connection = self._connect()
            try:
                for table, model in _TABLES.items():
                    columns = ", ".join(
                        f'{table}."{field.alias or name}"'
                        for name, field in model.model_fields.items()
                    )
                    connection.execute(f"SELECT {columns} FROM {table} LIMIT 0")
                connection.execute("SELECT form, lemma_id FROM form_index LIMIT 0")
                if connection.execute("PRAGMA quick_check").fetchall()[0][0] != "ok":
                    raise ValueError("SQLite integrity check failed")
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ValueError("dangling lexicon reference")
                if connection.execute("SELECT 1 FROM sense LIMIT 1").fetchone() is None:
                    raise ValueError("lexicon has no senses")
            finally:
                connection.close()
        except (sqlite3.Error, OSError, ValueError) as error:
            raise self._invalid(error) from error

    async def validate(self) -> None:
        """Check schema, integrity and nonempty senses without writing to the artifact."""
        await asyncio.to_thread(self._validate)

    def _read[T: LexiconRecord](
        self, model: type[T], sql: str, parameters: tuple[Any, ...]
    ) -> list[T]:
        try:
            connection = self._connect()
            try:
                records = []
                for row in connection.execute(sql, parameters):
                    values = dict(row)
                    for column, value in values.items():
                        structured_id = column == "id" and model in {
                            LexiconLemma,
                            LexiconLexeme,
                            LexiconSense,
                        }
                        if value is not None and (
                            column in _JSON_COLUMNS or column in _KEY_COLUMNS or structured_id
                        ):
                            values[column] = json.loads(value)
                    records.append(model.model_validate(values))
                return records
            finally:
                connection.close()
        except (sqlite3.Error, OSError, ValueError, ValidationError) as error:
            raise self._invalid(error) from error

    async def _many[T: LexiconRecord](self, model: type[T], sql: str, *parameters: Any) -> list[T]:
        return await asyncio.to_thread(self._read, model, sql, parameters)

    async def _one[T: LexiconRecord](
        self, model: type[T], table: str, key: DictionaryKey
    ) -> T | None:
        records = await self._many(model, f"SELECT * FROM {table} WHERE id = ?", _key(key))
        return records[0] if records else None

    async def get_lemma(self, text: str, *, lang: str = "en") -> LexiconLemma | None:
        return await self.get_lemma_by_id(lemma_key(lang, text))

    async def get_lemma_by_id(self, key: DictionaryKey) -> LexiconLemma | None:
        return await self._one(LexiconLemma, "lemma", key)

    async def lookup_form(self, text: str, *, lang: str = "en") -> list[LexiconLemma]:
        language, normalized = lemma_key(lang, text)
        return await self._many(
            LexiconLemma,
            "SELECT l.* FROM lemma l JOIN form_index f ON f.lemma_id = l.id "
            "WHERE f.form = ? AND l.lang = ? ORDER BY l.text, l.id",
            normalized,
            language,
        )

    async def get_lexeme(self, key: DictionaryKey) -> LexiconLexeme | None:
        return await self._one(LexiconLexeme, "lexeme", key)

    async def lexemes(
        self, lemma_id: DictionaryKey, *, pos: str | None = None
    ) -> list[LexiconLexeme]:
        return await self._many(
            LexiconLexeme,
            "SELECT * FROM lexeme WHERE lemma_id = ? AND (? IS NULL OR pos = ?) "
            "ORDER BY pos, etymology_no, id",
            _key(lemma_id),
            pos,
            pos,
        )

    async def get_sense(self, key: DictionaryKey) -> LexiconSense | None:
        return await self._one(LexiconSense, "sense", key)

    async def senses(
        self, lexeme_id: DictionaryKey, *, common_only: bool = False
    ) -> list[LexiconSense]:
        return await self._many(
            LexiconSense,
            "SELECT * FROM sense WHERE lexeme_id = ? AND (? = 0 OR common = 1) ORDER BY rank, id",
            _key(lexeme_id),
            common_only,
        )

    async def pronunciations(
        self, lexeme_id: DictionaryKey, *, accent: Accent | None = None
    ) -> list[LexiconPronunciation]:
        return await self._many(
            LexiconPronunciation,
            "SELECT * FROM pron WHERE lexeme_id = ? AND (? IS NULL OR accent = ?) "
            "ORDER BY accent, id",
            _key(lexeme_id),
            accent,
            accent,
        )

    async def forms(self, lexeme_id: DictionaryKey) -> list[LexiconForm]:
        return await self._many(
            LexiconForm,
            "SELECT * FROM form WHERE lexeme_id = ? ORDER BY form, tags, source",
            _key(lexeme_id),
        )

    async def relations(
        self,
        sense_id: DictionaryKey,
        *,
        type: RelationType | None = None,
        direction: RelationDirection = "outgoing",
    ) -> list[LexiconRelation]:
        if direction not in {"outgoing", "incoming"}:
            raise ValueError("direction must be outgoing or incoming")
        column = "source_sense_id" if direction == "outgoing" else "target_sense_id"
        return await self._many(
            LexiconRelation,
            f"SELECT * FROM relation WHERE {column} = ? AND (? IS NULL OR type = ?) "
            "ORDER BY type, source_sense_id, target_sense_id, source",
            _key(sense_id),
            type,
            type,
        )

    async def glosses(self, lexeme_id: DictionaryKey) -> list[LexiconGloss]:
        return await self._many(
            LexiconGloss,
            "SELECT * FROM zh_gloss WHERE lexeme_id = ? ORDER BY gloss, source",
            _key(lexeme_id),
        )

    async def tags(self, lemma_id: DictionaryKey) -> list[LexiconTag]:
        return await self._many(
            LexiconTag,
            "SELECT * FROM exam_tag WHERE lemma_id = ? ORDER BY tag, source",
            _key(lemma_id),
        )

    async def frequencies(self, lemma_id: DictionaryKey) -> list[LexiconFrequency]:
        return await self._many(
            LexiconFrequency,
            "SELECT * FROM freq WHERE lemma_id = ? ORDER BY source",
            _key(lemma_id),
        )

    async def affixes(self, lexeme_id: DictionaryKey) -> list[LexiconAffix]:
        return await self._many(
            LexiconAffix,
            "SELECT * FROM affix WHERE lexeme_id = ? ORDER BY position, source",
            _key(lexeme_id),
        )

    async def affixes_for_root(self, text: str, *, lang: str = "en") -> list[LexiconAffix]:
        language, normalized = lemma_key(lang, text)
        return await self._many(
            LexiconAffix,
            "SELECT a.* FROM affix a JOIN lexeme x ON a.lexeme_id = x.id "
            "JOIN lemma l ON x.lemma_id = l.id WHERE a.type = 'root' AND a.text = ? "
            "AND l.lang = ? ORDER BY a.lexeme_id, a.position, a.source",
            normalized,
            language,
        )

    async def sources(self) -> list[LexiconSource]:
        return await self._many(LexiconSource, "SELECT * FROM source ORDER BY name")
