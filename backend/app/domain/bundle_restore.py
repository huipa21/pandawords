"""Import-side helpers: resolve bundle references to database IDs and rebuild row content."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from surrealdb import RecordID

from app.core.errors import BundleError
from app.domain.bundle_edges import EdgeEntry
from app.domain.bundle_refs import parse_ref, shared_record

REF_FIELDS = frozenset({"from", "to", "project", "target", "sense", "audio"})
_ENTRY_ONLY = frozenset({"table", "ref", "owner", "identity", "file", "from", "to"})


class RefResolver:
    """Shared refs map to deterministic IDs; local refs to IDs the importer allocated."""

    def __init__(self, local: Mapping[str, RecordID]) -> None:
        self.local = dict(local)

    def __call__(self, ref: str) -> RecordID:
        parsed = parse_ref(ref)
        if parsed.shared:
            return shared_record(ref)
        try:
            return self.local[ref]
        except KeyError:
            raise BundleError("dangling_reference", "references", [parsed.table]) from None


def _resolve(value: Any, resolve: RefResolver, key: str | None) -> Any:
    if isinstance(value, dict):
        return {k: _resolve(v, resolve, k) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [_resolve(item, resolve, None) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if key in REF_FIELDS and isinstance(value, str):
        return resolve(value)
    return value


def entry_fields(entry: BaseModel, resolve: RefResolver) -> dict[str, Any]:
    """Database field values for an entry (ownership and IDs are set by the importer).

    Override ``fields`` are user data and are copied verbatim, never resolved.
    """
    dumped = entry.model_dump(mode="python", by_alias=True, exclude_none=True)
    overlay = dumped.pop("fields", None)
    values = {
        key: _resolve(value, resolve, key)
        for key, value in dumped.items()
        if key not in _ENTRY_ONLY
    }
    if overlay is not None:
        values["fields"] = overlay
    return values


def edge_endpoints(edge: EdgeEntry, resolve: RefResolver) -> tuple[RecordID, RecordID]:
    return resolve(edge.from_), resolve(edge.to)


def shared_edge_id(edge: EdgeEntry) -> RecordID:
    """Deterministic ID ``table:[from, to, *identity]`` used to merge shared edges."""
    if edge.owner != "shared":
        raise ValueError("Only shared edges have deterministic IDs")
    return RecordID(edge.table, [shared_record(edge.from_), shared_record(edge.to), *edge.identity])
