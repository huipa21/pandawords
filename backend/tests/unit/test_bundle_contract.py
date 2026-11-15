import json
import random
from collections.abc import Callable, Mapping
from typing import Any

import pytest
from surrealdb import RecordID

from app.core.errors import BundleError
from app.domain.bundle import SCHEMA_PATH, BundleData, dump_data, parse_data, schema_text
from app.domain.bundle_edges import EDGE_MODELS
from app.domain.bundle_manifest import parse_manifest
from app.domain.bundle_records import RECORD_MODELS
from app.domain.bundle_refs import RefAllocator
from app.domain.bundle_restore import RefResolver, edge_endpoints, entry_fields, shared_edge_id
from app.domain.bundle_serialize import BundleSource, serialize_bundle
from app.domain.bundle_validate import validate_bundle
from tests import bundle_support as fx


def _bundle(source: BundleSource | None = None, fmt: Any = "pandawords.user") -> BundleData:
    return serialize_bundle(fx.OWNER, fmt, source or fx.source())


def _shared(row: Mapping[str, Any]) -> bool:
    return row.get("owner") is None and row["id"].table_name != "media"


def _raw() -> dict[str, Any]:
    return json.loads(dump_data(_bundle()))


def _reject(data: dict[str, Any]) -> BundleError:
    with pytest.raises(BundleError) as caught:
        validate_bundle(parse_data(json.dumps(data).encode()))
    return caught.value


def test_schema_file_is_generated_from_models() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == schema_text()


def test_round_trip_covers_every_category_and_restores_rows() -> None:
    source = fx.source()
    raw = dump_data(_bundle(source))
    data = parse_data(raw)
    index = validate_bundle(data)
    assert dump_data(data) == raw
    assert {record.table for record in data.records} == set(RECORD_MODELS)
    assert {edge.table for edge in data.edges} == set(EDGE_MODELS)
    assert data.preferences is not None and data.preferences.accent == "UK"
    assert [(i.hidden, i.study_order) for i in data.includes if i.study_order is not None] == [
        (True, 0),
        (False, 1),
    ]

    rows = [*source.records, *source.projects, *source.notes, *source.media]
    allocator = RefAllocator(fx.OWNER, [(row["id"], row.get("owner")) for row in rows])
    local = {allocator.ref(row["id"]): row["id"] for row in rows if not _shared(row)}
    assert set(local) == {*index.projects, *index.notes, *index.media} | {
        ref for ref, record in index.records.items() if record.owner == "owned"
    }
    originals = {row["id"]: row for row in rows}
    resolve = RefResolver(local)

    for record in data.records:
        row = originals[resolve(record.ref)]
        assert entry_fields(record, resolve) == {
            k: v for k, v in row.items() if k not in {"id", "owner"}
        }
    source_edges = {(r["id"].table_name, r["in"], r["out"]): r for r in source.edges}
    for edge in data.edges:
        start, end = edge_endpoints(edge, resolve)
        row = source_edges[(edge.table, start, end)]
        expected = {k: v for k, v in row.items() if k not in {"id", "owner", "in", "out"}}
        assert entry_fields(edge, resolve) == expected
        if edge.owner == "shared":
            assert shared_edge_id(edge) == row["id"]
    note = entry_fields(data.notes[0], resolve)
    assert note == {"target": fx.SENSE, "kind": "mnemonic", "text": "run = 润"}
    override = entry_fields(data.overrides[0], resolve)
    assert override["target"] == fx.SENSE and override["fields"]["gloss"] == {"zh": "奔跑"}
    memory = entry_fields(data.memory[0], resolve)
    assert memory["sense"] == fx.SENSE and memory["card"]["card_id"] == 17
    logs = {log.attempt_id: log for log in data.review_log}
    assert logs["attempt-1"].card_after is not None and logs["attempt-0"].card_after is None
    assert logs["attempt-0"].project is None  # deleted project is not part of the bundle
    assert resolve(logs["attempt-1"].project or "") == fx.PROJECT


def test_serialization_is_stable_and_hides_private_identifiers() -> None:
    first = dump_data(_bundle())
    shuffled = fx.source()
    rng = random.Random(7)
    for name in ("records", "edges", "includes", "media", "review_log"):
        rows = list(getattr(shuffled, name))
        rng.shuffle(rows)
        setattr(shuffled, name, rows)
    assert dump_data(_bundle(shuffled)) == first
    text = first.decode()
    for secret in ("alice", "argon2", "secret", "own-sense", "project-x4", "media-img", "path"):
        assert secret not in text
    assert "sense:@1" in text and "project:@1" in text and "media:@2" in text


def test_foreign_rows_are_never_serialized() -> None:
    other = RecordID("user", "bob")
    for name, mutate in (
        ("records", lambda rows: rows[-1].update(owner=other)),
        ("edges", lambda rows: rows[-1].update(owner=other)),
        ("projects", lambda rows: rows[0].update(owner=other)),
        ("media", lambda rows: rows[0].update(owner=other)),
    ):
        source = fx.source()
        rows = [dict(row) for row in getattr(source, name)]
        mutate(rows)
        setattr(source, name, rows)
        with pytest.raises(BundleError) as caught:
            _bundle(source)
        assert caught.value.code == "bundle.foreign_owner", name


def test_project_bundle_scope() -> None:
    data = _bundle(fmt="pandawords.project")
    with pytest.raises(BundleError) as caught:
        validate_bundle(data)  # project bundles never carry preferences
    assert caught.value.code == "bundle.project_scope"
    source = fx.source()
    source.user = None
    validate_bundle(_bundle(source, "pandawords.project"))


def _set(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def apply(data: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        target: Any = data
        for part in parents:
            target = target[int(part)] if part.isdigit() else target[part]
        if value is KeyError:
            del target[int(last) if last.isdigit() else last]
        else:
            target[int(last) if last.isdigit() else last] = value

    return apply


def _first(data: dict[str, Any], name: str, **match: Any) -> int:
    return next(
        i for i, item in enumerate(data[name]) if all(item.get(k) == v for k, v in match.items())
    )


@pytest.mark.parametrize(
    ("name", "mutate", "reason"),
    [
        ("missing field", lambda d: _set("records.0.text", KeyError)(d), "invalid_data"),
        ("wrong type", lambda d: _set("records.0.freq_zipf", "high")(d), "invalid_data"),
        ("bool as int", lambda d: _set("memory.0.card.state", True)(d), "invalid_data"),
        ("unknown field", lambda d: _set("projects.0.password_hash", "x")(d), "invalid_data"),
        ("newer schema", lambda d: _set("schema_revision", 2)(d), "unsupported_schema"),
        ("site data", lambda d: _set("format", "pandawords.site")(d), "unexpected_format"),
        ("bad ref", lambda d: _set("includes.0.target", "sense:@0")(d), "invalid_data"),
        ("noncanonical", lambda d: _set("records.0.ref", 'lemma:[ "en","run"]')(d), "invalid_data"),
        (
            "dangling include",
            lambda d: _set("includes.0.target", "sense:@99")(d),
            "invalid_references",
        ),
        ("dangling edge", lambda d: _set("edges.0.to", "lexeme:@7")(d), "invalid_references"),
        (
            "dangling log",
            lambda d: _set("review_log.0.project", "project:@5")(d),
            "invalid_references",
        ),
        (
            "dangling audio",
            lambda d: _set(
                f"records.{_first(d, 'records', table='lexeme', pos='verb')}.pron.0.audio",
                "media:@9",
            )(d),
            "invalid_references",
        ),
        ("owner mismatch", lambda d: _set("records.0.owner", "owned")(d), "invalid_references"),
        (
            "shared edge to owned",
            lambda d: _set(f"edges.{_first(d, 'edges', table='part_of')}.owner", "shared")(d),
            "invalid_references",
        ),
        (
            "owned edge identity",
            lambda d: _set(f"edges.{_first(d, 'edges', table='part_of')}.identity", [1])(d),
            "invalid_references",
        ),
        (
            "edge endpoint table",
            lambda d: _set(
                f"edges.{_first(d, 'edges', table='has_lexeme')}.to", 'lemma:["en","run"]'
            )(d),
            "invalid_references",
        ),
        (
            "override owner key",
            lambda d: _set("overrides.0.fields.owner", "user:x")(d),
            "invalid_references",
        ),
        (
            "unsafe media file",
            lambda d: _set("media.0.file", "media/../../etc/passwd")(d),
            "invalid_data",
        ),
        ("media path field", lambda d: _set("media.0.path", "image/a/b.png")(d), "invalid_data"),
        (
            "media mime",
            lambda d: _set(f"media.{_first(d, 'media', kind='image')}.mime", "image/svg+xml")(d),
            "invalid_media",
        ),
        (
            "media accent",
            lambda d: _set(f"media.{_first(d, 'media', kind='image')}.accent", "US")(d),
            "invalid_media",
        ),
        (
            "shared media owned target",
            lambda d: _set(f"media.{_first(d, 'media', kind='audio')}.target", "sense:@1")(d),
            "invalid_media",
        ),
    ],
)
def test_invalid_bundles_are_rejected(
    name: str, mutate: Callable[[dict[str, Any]], None], reason: str
) -> None:
    data = _raw()
    mutate(data)
    assert _reject(data).code == f"bundle.{reason}", name


def test_manifest_versions_fail_explicitly() -> None:
    base = json.loads(fx.header().model_dump_json()) | {
        "entries": [{"path": "data.json", "sha256": "0" * 64, "size": 1}]
    }
    assert parse_manifest(json.dumps(base).encode()).version == 1
    for patch, reason in (
        ({"version": 2}, "unsupported_version"),
        ({"version": "1"}, "malformed_manifest"),
        ({"schema_revision": 9}, "unsupported_schema"),
        ({"format": "other.format"}, "malformed_manifest"),
        (
            {"entries": [{"path": "../data.json", "sha256": "0" * 64, "size": 1}]},
            "malformed_manifest",
        ),
        ({"entries": []}, "missing_entry"),
    ):
        with pytest.raises(BundleError) as caught:
            parse_manifest(json.dumps(base | patch).encode())
        assert caught.value.code == f"bundle.{reason}"
    with pytest.raises(BundleError) as caught:
        parse_manifest(json.dumps(base).encode(), frozenset({"pandawords.project"}))
    assert caught.value.code == "bundle.unexpected_format"
