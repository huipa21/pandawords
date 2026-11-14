"""Owner-safe effective records, tree ancestry and graph-neighbour lookups."""

from typing import Any, Literal, cast
from uuid import UUID

from pydantic import JsonValue
from surrealdb import AsyncSurrealConnection, RecordID

from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.domain.dictionary import (
    DictionaryEdgeRead,
    DictionaryEntryRead,
    DictionaryLexemeRead,
    DictionaryRecordRead,
    DictionaryRelation,
    DictionaryTable,
)
from app.domain.identity import user_key, user_subject

TABLE_FIELDS: dict[str, set[str]] = {
    "lemma": {
        "text",
        "lang",
        "kind",
        "freq_zipf",
        "cefr",
        "exam_tags",
        "source",
        "frequencies",
        "exam_tag_sources",
    },
    "lexeme": {"pos", "etymology_no", "etymology_text", "forms", "pron"},
    "sense": {"definition", "gloss", "register", "domain", "examples", "rank", "common", "source"},
    "morpheme": {"text", "type", "meaning"},
    "tag": {"kind", "name"},
    "sentence": {"text", "lang", "translation", "source"},
    "passage": {"title", "text", "lang", "source"},
}
RELATIONS = (
    "has_lexeme",
    "has_sense",
    "composed_of",
    "derives_to",
    "relates_to",
    "member_of",
    "contains",
    "used_in",
    "part_of",
)


def _check(record: RecordID) -> None:
    if record.table_name not in TABLE_FIELDS:
        raise ValueError("Unsupported dictionary table")


def _json(value: Any) -> JsonValue:
    if isinstance(value, RecordID):
        return encode_rid(value, value.table_name)
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json(item) for item in value]
    return value


def _merge(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


async def _record(
    db: AsyncSurrealConnection, user: RecordID, target: RecordID, txn: UUID
) -> DictionaryRecordRead | None:
    _check(target)
    rows = await _rows(
        db,
        "SELECT * FROM $target WHERE owner = NONE OR owner = $user;",
        {"target": target, "user": user},
        txn_id=txn,
    )
    if not rows:
        return None
    row = rows[0]
    overlays = await _rows(
        db,
        "SELECT fields FROM $overlay WHERE owner = $user;",
        {"overlay": RecordID("override", [user, target]), "user": user},
        txn_id=txn,
    )
    allowed = TABLE_FIELDS[target.table_name]
    fields = {key: value for key, value in row.items() if key in allowed}
    if overlays:
        changes = {key: value for key, value in overlays[0]["fields"].items() if key in allowed}
        fields = _merge(fields, changes)
    return DictionaryRecordRead(
        id=encode_rid(target, target.table_name),
        table=cast(DictionaryTable, target.table_name),
        owner=user_subject(str(row["owner"].id)) if row.get("owner") is not None else None,
        fields={key: _json(value) for key, value in fields.items()},
    )


async def read_records(
    db: AsyncSurrealConnection, owner: str, targets: list[RecordID]
) -> list[DictionaryRecordRead]:
    """Preserve request order; omit absent and unauthorized targets identically."""
    for target in targets:
        _check(target)

    async def operation(txn: UUID) -> list[DictionaryRecordRead]:
        user = RecordID("user", user_key(owner))
        records = [await _record(db, user, target, txn) for target in targets]
        return [record for record in records if record is not None]

    return await _atomic(db, operation)


async def _edges(
    db: AsyncSurrealConnection,
    user: RecordID,
    target: RecordID,
    relation: DictionaryRelation | None,
    direction: Literal["outgoing", "incoming", "both"],
    txn: UUID,
) -> list[dict[str, Any]]:
    queries = {
        "outgoing": (
            "SELECT ->(? WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user)).* AS edges "
            "FROM $target WHERE owner = NONE OR owner = $user;"
        ),
        "incoming": (
            "SELECT <-(? WHERE (owner = NONE OR owner = $user) "
            "AND (in.owner = NONE OR in.owner = $user) "
            "AND (out.owner = NONE OR out.owner = $user)).* AS edges "
            "FROM $target WHERE owner = NONE OR owner = $user;"
        ),
    }
    edges: dict[str, dict[str, Any]] = {}
    directions = ("outgoing", "incoming") if direction == "both" else (direction,)
    for selected in directions:
        rows = await _rows(db, queries[selected], {"target": target, "user": user}, txn_id=txn)
        for row in rows:
            for edge in row["edges"]:
                table = edge["id"].table_name
                if table in RELATIONS and (relation is None or table == relation):
                    edges[encode_rid(edge["id"], table)] = edge
    return list(edges.values())


async def read_edges(
    db: AsyncSurrealConnection,
    owner: str,
    target: RecordID,
    *,
    relation: DictionaryRelation | None = None,
    direction: Literal["outgoing", "incoming", "both"] = "both",
) -> list[DictionaryEdgeRead]:
    _check(target)
    if relation is not None and relation not in RELATIONS:
        raise ValueError("Unsupported dictionary relation")
    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError("Unsupported edge direction")

    async def operation(txn: UUID) -> list[DictionaryEdgeRead]:
        user = RecordID("user", user_key(owner))
        if await _record(db, user, target, txn) is None:
            return []
        result: list[DictionaryEdgeRead] = []
        for row in await _edges(db, user, target, relation, direction, txn):
            if await _record(db, user, row["in"], txn) is None:
                continue
            if await _record(db, user, row["out"], txn) is None:
                continue
            table = row["id"].table_name
            result.append(
                DictionaryEdgeRead(
                    id=encode_rid(row["id"], table),
                    table=cast(DictionaryRelation, table),
                    start=encode_rid(row["in"], row["in"].table_name),
                    end=encode_rid(row["out"], row["out"].table_name),
                    owner=user_subject(str(row["owner"].id)) if row.get("owner") else None,
                    fields={
                        key: _json(value)
                        for key, value in row.items()
                        if key not in {"id", "in", "out", "owner"}
                    },
                )
            )
        return sorted(result, key=lambda edge: edge.id)

    return await _atomic(db, operation)


async def read_entry(
    db: AsyncSurrealConnection, owner: str, lemma: RecordID
) -> DictionaryEntryRead | None:
    if lemma.table_name != "lemma":
        raise ValueError("Expected lemma ID")

    async def operation(txn: UUID) -> DictionaryEntryRead | None:
        user = RecordID("user", user_key(owner))
        record = await _record(db, user, lemma, txn)
        if record is None:
            return None
        lexemes: dict[str, DictionaryLexemeRead] = {}
        for edge in await _edges(db, user, lemma, "has_lexeme", "outgoing", txn):
            lexeme = await _record(db, user, edge["out"], txn)
            if lexeme is None or lexeme.id in lexemes:
                continue
            senses: dict[str, DictionaryRecordRead] = {}
            for sense_edge in await _edges(db, user, edge["out"], "has_sense", "outgoing", txn):
                sense = await _record(db, user, sense_edge["out"], txn)
                if sense is not None:
                    senses[sense.id] = sense
            lexemes[lexeme.id] = DictionaryLexemeRead(
                lexeme=lexeme,
                senses=sorted(
                    senses.values(), key=lambda sense: (cast(int, sense.fields["rank"]), sense.id)
                ),
            )
        return DictionaryEntryRead(
            lemma=record, lexemes=sorted(lexemes.values(), key=lambda item: item.lexeme.id)
        )

    return await _atomic(db, operation)
