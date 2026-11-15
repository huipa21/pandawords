"""``data.json`` contract: typed model, canonical serialization and JSON Schema generation.

The committed ``bundle.schema.json`` is generated from :class:`BundleData`; a unit test fails
if it drifts. Regenerate with ``uv run python -m app.domain.bundle``.
"""

import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, ValidationError

from app.core.errors import BundleError
from app.domain.bundle_edges import EdgeEntry, Entry
from app.domain.bundle_manifest import SCHEMA_REVISION, BundleFormat
from app.domain.bundle_records import DictRecord
from app.domain.bundle_user import (
    IncludeEntry,
    MediaEntry,
    MemoryEntry,
    NoteEntry,
    OverrideEntry,
    Preferences,
    ProjectEntry,
    ReviewLogEntry,
)

SCHEMA_PATH = Path(__file__).with_name("bundle.schema.json")
MAX_DATA_BYTES = 256 * 1024 * 1024
_MAX_ITEMS = 1_000_000


type Items[T] = Annotated[list[T], Field(max_length=_MAX_ITEMS)]


class BundleData(Entry):
    format: BundleFormat
    schema_revision: int
    records: Items[DictRecord] = []
    edges: Items[EdgeEntry] = []
    projects: Items[ProjectEntry] = []
    includes: Items[IncludeEntry] = []
    overrides: Items[OverrideEntry] = []
    notes: Items[NoteEntry] = []
    media: Items[MediaEntry] = []
    memory: Items[MemoryEntry] = []
    review_log: Items[ReviewLogEntry] = []
    preferences: Preferences | None = None


def _edge_key(edge: Any) -> str:
    return json.dumps(edge, sort_keys=True, ensure_ascii=False)


_SORT_KEYS: dict[str, Any] = {
    "records": lambda item: (item["table"], item["ref"]),
    "edges": lambda item: (item["table"], item["from"], item["to"], _edge_key(item)),
    "projects": lambda item: item["ref"],
    "includes": lambda item: (item["project"], item["target"]),
    "overrides": lambda item: item["target"],
    "notes": lambda item: item["ref"],
    "media": lambda item: item["ref"],
    "memory": lambda item: item["sense"],
    "review_log": lambda item: (item["at"], item["attempt_id"]),
}


def canonical(data: BundleData) -> dict[str, Any]:
    """JSON-ready dict with collections in canonical order (list contents keep their order)."""
    dumped = data.model_dump(mode="json", by_alias=True)
    for name, key in _SORT_KEYS.items():
        dumped[name] = sorted(dumped[name], key=key)
    return dumped


def dump_data(data: BundleData) -> bytes:
    """Deterministic UTF-8 bytes: same logical input always yields identical output."""
    text = json.dumps(canonical(data), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return (text + "\n").encode()


def _problems(error: ValidationError) -> list[str]:
    return [
        ".".join(str(part) for part in item["loc"]) + ": " + item["type"]
        for item in error.errors(include_url=False, include_input=False)[:20]
    ]


def parse_data(raw: bytes) -> BundleData:
    """Schema-validate ``data.json``; cross-record checks live in ``bundle_validate``."""
    if len(raw) > MAX_DATA_BYTES:
        raise BundleError("data_too_large", "data")
    try:
        probe = json.loads(raw)
    except ValueError, RecursionError:
        raise BundleError("malformed_data", "data") from None
    if isinstance(probe, dict):
        revision = probe.get("schema_revision")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if type(revision) is int and revision > SCHEMA_REVISION:
            raise BundleError("unsupported_schema", "data", [f"schema_revision: {revision}"])
    try:
        return BundleData.model_validate_json(raw)
    except ValidationError as error:
        raise BundleError("invalid_data", "data", _problems(error)) from None


def json_schema() -> dict[str, Any]:
    schema = BundleData.model_json_schema(by_alias=True, mode="validation")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://pandawords.local/schemas/bundle-data-{SCHEMA_REVISION}.json",
        **schema,
    }


def schema_text() -> str:
    return json.dumps(json_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    SCHEMA_PATH.write_text(schema_text(), encoding="utf-8", newline="\n")
