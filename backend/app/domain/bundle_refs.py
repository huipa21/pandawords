"""Bundle-local reference grammar shared by export, validation and import.

* Shared dictionary rows (``owner = NONE``) keep their deterministic identity:
  ``<table>:<canonical JSON key>``, e.g. ``lemma:["en","run"]``.
* Owner-owned rows (and shared media, whose IDs are random) never expose a database ID:
  ``<table>:@<n>``, numbered per table in the sorted order of their source IDs, so repeated
  exports of the same data are byte-identical.
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, get_args

from surrealdb import RecordID

from app.core.errors import BundleError

type DictTable = Literal["lemma", "lexeme", "sense", "morpheme", "tag", "sentence", "passage"]
type OwnedTable = Literal["project", "note", "media"]
type SharedKey = str | int | list[SharedKey]

DICT_TABLES: frozenset[str] = frozenset(get_args(DictTable.__value__))
OWNED_TABLES: frozenset[str] = frozenset(get_args(OwnedTable.__value__))
REF_TABLES = DICT_TABLES | OWNED_TABLES
REF_PATTERN = (
    r"^(?:(?:lemma|lexeme|sense|morpheme|tag|sentence|passage|project|note|media):@[1-9][0-9]{0,8}"
    r"|(?:lemma|lexeme|sense|morpheme|tag|sentence|passage):[\[\"0-9-].{0,2047})$"
)
_LOCAL = re.compile(r"([a-z]+):@([1-9][0-9]{0,8})")
_MAX_KEY_DEPTH = 8


@dataclass(frozen=True, slots=True)
class ParsedRef:
    table: str
    shared_key: SharedKey | None = None
    local: int | None = None

    @property
    def shared(self) -> bool:
        return self.local is None


def _check_key(value: object, depth: int = 0) -> SharedKey:
    if depth > _MAX_KEY_DEPTH:
        raise ValueError("Shared key is too deeply nested")
    if type(value) is str:
        if not value or len(value) > 512:
            raise ValueError("Invalid shared key text")
        return value
    if type(value) is int:
        if not -(2**63) <= value < 2**63:
            raise ValueError("Shared key integer is out of range")
        return value
    if type(value) is list and value:
        return [_check_key(item, depth + 1) for item in value]  # pyright: ignore[reportUnknownVariableType]
    raise ValueError("Unsupported shared key")


def canonical_key(key: SharedKey) -> str:
    return json.dumps(_check_key(key), ensure_ascii=False, separators=(",", ":"))


def shared_ref(table: str, key: object) -> str:
    if table not in DICT_TABLES:
        raise ValueError("Only dictionary tables have shared references")
    return f"{table}:{canonical_key(_check_key(key))}"


def local_ref(table: str, number: int) -> str:
    if table not in REF_TABLES or not 0 < number < 10**9:
        raise ValueError("Invalid local reference")
    return f"{table}:@{number}"


def parse_ref(ref: str) -> ParsedRef:
    """Parse a reference; shared keys must be in canonical form so equality is textual."""
    if not isinstance(ref, str) or len(ref) > 2100:
        raise ValueError("Invalid reference")
    if match := _LOCAL.fullmatch(ref):
        if match[1] not in REF_TABLES:
            raise ValueError("Invalid reference table")
        return ParsedRef(match[1], local=int(match[2]))
    table, _, raw = ref.partition(":")
    if table not in DICT_TABLES or not raw:
        raise ValueError("Invalid reference")
    try:
        key = _check_key(json.loads(raw))
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid shared reference key") from error
    if canonical_key(key) != raw:
        raise ValueError("Shared reference key is not canonical")
    return ParsedRef(table, shared_key=key)


def shared_record(ref: str) -> RecordID:
    """Deterministic database ID of a shared dictionary reference."""
    parsed = parse_ref(ref)
    if parsed.shared_key is None:
        raise ValueError("Not a shared reference")
    return RecordID(parsed.table, parsed.shared_key)


def _stable(value: object) -> object:
    if isinstance(value, RecordID):
        return [value.table_name, _stable(value.id)]
    if isinstance(value, list):
        return [_stable(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, dict):
        return {str(k): _stable(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    return value


def _sort_text(record: RecordID) -> str:
    return json.dumps(_stable(record.id), sort_keys=True, ensure_ascii=False, default=str)


class RefAllocator:
    """Maps source ``RecordID``s to bundle refs for one exporting owner."""

    def __init__(
        self, owner: RecordID, records: Iterable[tuple[RecordID, RecordID | None]]
    ) -> None:
        self._refs: dict[tuple[str, str], str] = {}
        owned: dict[str, list[RecordID]] = {}
        for record, record_owner in records:
            table = record.table_name
            if table not in REF_TABLES:
                raise BundleError("unsupported_record", "references", [table])
            if record_owner is None and table == "media":
                # Shared pronunciation audio has random IDs: number it bundle-locally.
                owned.setdefault(table, []).append(record)
            elif record_owner is None:
                if table not in DICT_TABLES:
                    raise BundleError("unsupported_owner", "references", [table])
                try:
                    ref = shared_ref(table, record.id)
                except ValueError:
                    raise BundleError("shared_identity", "references", [table]) from None
                self._refs[(table, _sort_text(record))] = ref
            elif record_owner == owner:
                owned.setdefault(table, []).append(record)
            else:
                raise BundleError("foreign_owner", "references", [table])
        for table, items in owned.items():
            unique = sorted({_sort_text(item) for item in items})
            for number, text in enumerate(unique, start=1):
                key = (table, text)
                if key in self._refs:
                    raise BundleError("owner_conflict", "references", [table])
                self._refs[key] = local_ref(table, number)

    def ref(self, record: RecordID) -> str:
        try:
            return self._refs[(record.table_name, _sort_text(record))]
        except KeyError:
            raise BundleError("dangling_reference", "references", [record.table_name]) from None

    def known(self, record: RecordID) -> bool:
        return (record.table_name, _sort_text(record)) in self._refs
