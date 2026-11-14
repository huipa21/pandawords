"""Bounded, canonical record-ID transport; never a general SurrealQL parser."""

import base64
import binascii
import json
import math
import re
from typing import cast

from surrealdb import RecordID

type _Value = str | int | float | bool | None | RecordID | list[_Value] | dict[str, _Value]

_TABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BARE = re.compile(r"[A-Za-z0-9_]+")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,16384}")
_JSON = json.JSONDecoder()
_MAX_DEPTH = 32


def _table(table: str) -> None:
    if not isinstance(table, str) or not _TABLE.fullmatch(table):
        raise ValueError("Invalid record table")


def _render_record(record: RecordID, depth: int) -> str:
    if depth > _MAX_DEPTH:
        raise ValueError("Record ID is too deeply nested")
    _table(record.table_name)
    key = record.id
    if type(key) not in (str, int, list, dict):
        raise ValueError("Unsupported record key")
    if isinstance(key, str) and _BARE.fullmatch(key) and not key.isdecimal():
        identifier = key
    else:
        identifier = _render(cast(_Value, key), depth + 1)
    return f"{record.table_name}:{identifier}"


def _render(value: _Value, depth: int) -> str:
    if depth > _MAX_DEPTH:
        raise ValueError("Record ID is too deeply nested")
    if isinstance(value, RecordID):
        return _render_record(value, depth)
    if type(value) is list:
        return "[" + ",".join(_render(item, depth + 1) for item in value) + "]"
    if type(value) is dict:
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Record object keys must be strings")
        return (
            "{"
            + ",".join(
                json.dumps(key, ensure_ascii=False) + ":" + _render(value[key], depth + 1)
                for key in sorted(value)
            )
            + "}"
        )
    if type(value) is int:
        if not -(2**63) <= value < 2**63:
            raise ValueError("Record integer is out of range")
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Non-finite record number")
    elif type(value) not in (str, bool, type(None)):
        raise ValueError("Unsupported record value")
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.position = 0

    def _take(self, token: str) -> bool:
        if self.text.startswith(token, self.position):
            self.position += len(token)
            return True
        return False

    def _expect(self, token: str) -> None:
        if not self._take(token):
            raise ValueError("Malformed record ID")

    def record(self, depth: int = 0) -> RecordID:
        match = _TABLE.match(self.text, self.position)
        if match is None:
            raise ValueError("Malformed record table")
        self.position = match.end()
        self._expect(":")
        bare = _BARE.match(self.text, self.position)
        if bare and not bare.group().isdecimal():
            self.position = bare.end()
            key: _Value = bare.group()
        else:
            key = self.value(depth + 1)
        if type(key) not in (str, int, list, dict):
            raise ValueError("Unsupported record key")
        return RecordID(match.group(), cast(str | int | list | dict, key))

    def value(self, depth: int) -> _Value:
        if depth > _MAX_DEPTH:
            raise ValueError("Record ID is too deeply nested")
        if self._take("["):
            items: list[_Value] = []
            if not self._take("]"):
                while True:
                    items.append(self.value(depth + 1))
                    if self._take("]"):
                        break
                    self._expect(",")
            return items
        if self._take("{"):
            obj: dict[str, _Value] = {}
            if not self._take("}"):
                while True:
                    key = self.value(depth + 1)
                    if not isinstance(key, str) or key in obj:
                        raise ValueError("Invalid record object key")
                    self._expect(":")
                    obj[key] = self.value(depth + 1)
                    if self._take("}"):
                        break
                    self._expect(",")
            return obj
        table = _TABLE.match(self.text, self.position)
        if table and self.text.startswith(":", table.end()):
            return self.record(depth)
        value, self.position = _JSON.raw_decode(self.text, self.position)
        if type(value) not in (str, int, float, bool, type(None)):
            raise ValueError("Unsupported record value")
        return cast(_Value, value)


def encode_rid(record: RecordID, expected_table: str) -> str:
    """Encode a supported SDK RecordID as unpadded base64url UTF-8 record text."""
    _table(expected_table)
    if not isinstance(record, RecordID) or record.table_name != expected_table:
        raise ValueError("Unexpected record table")
    try:
        text = _render_record(record, 0)
        token = base64.urlsafe_b64encode(text.encode()).decode("ascii").rstrip("=")
        if not _TOKEN.fullmatch(token):
            raise ValueError("Record ID is too long")
        return token
    except RecursionError, UnicodeError:
        raise ValueError("Invalid record ID") from None


def decode_rid(value: str, expected_table: str) -> RecordID:
    """Decode only canonical IDs for the caller's expected resource table."""
    _table(expected_table)
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError("Invalid record ID")
    try:
        text = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        ).decode("utf-8")
        parser = _Parser(text)
        record = parser.record()
        if parser.position != len(text) or encode_rid(record, expected_table) != value:
            raise ValueError("Non-canonical record ID")
        return record
    except ValueError, UnicodeError, binascii.Error, RecursionError:
        raise ValueError("Invalid record ID") from None
