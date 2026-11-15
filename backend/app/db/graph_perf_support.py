"""Reproducible, isolated graph workloads and query-plan probes."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.dictionary import RELATIONS
from app.db.dictionary_schema_test_support import create
from app.db.migration_store import checked_query


@dataclass
class Workload:
    nodes: list[RecordID]
    edges: list[RecordID]
    excluded_nodes: list[RecordID]
    excluded_edges: list[RecordID]


async def workload(
    db: AsyncWsSurrealConnection, user: RecordID, other: RecordID, size: int
) -> Workload:
    project = RecordID("project", uuid4().hex)
    now = datetime(2026, 11, 14, tzinfo=UTC)
    await create(
        db,
        project,
        {
            "owner": user,
            "name": "Performance",
            "description": "",
            "target_lang": "en",
            "source_lang": "zh",
            "plan": {"daily_new": 10},
            "created_at": now,
        },
    )
    records: list[dict[str, Any]] = []
    selected: list[RecordID] = []
    memberships: list[dict[str, Any]] = []

    def node(table: str, fields: dict[str, Any], owner: RecordID | None) -> RecordID:
        record = RecordID(table, uuid4().hex)
        if owner is not None:
            fields["owner"] = owner
        records.append({"record": record, "content": fields})
        return record

    def select(table: str, fields: dict[str, Any], index: int) -> RecordID:
        owner = user if table in {"tag", "morpheme"} or index % 2 else None
        record = node(table, fields, owner)
        selected.append(record)
        if owner is None:
            memberships.append(
                {
                    "start": project,
                    "edge": RecordID("includes", uuid4().hex),
                    "end": record,
                    "content": {"owner": user, "hidden": False, "added_at": now},
                }
            )
        return record

    def sense_fields() -> dict[str, Any]:
        return {
            "definition": "Measured sense",
            "gloss": {"zh": "意思"},
            "register": [],
            "domain": [],
            "examples": [],
            "rank": 0,
            "common": True,
            "source": "fixture",
        }

    root = select(
        "lemma",
        {
            "text": uuid4().hex,
            "lang": "en",
            "kind": "phrase",
            "freq_zipf": 1,
            "exam_tags": [],
            "source": "fixture",
        },
        0,
    )
    lexemes = [
        select("lexeme", {"pos": "noun", "etymology_no": 1, "forms": [], "pron": []}, i)
        for i in range(size // 10)
    ]
    senses = [select("sense", sense_fields(), i) for i in range(size // 5)]
    leaves: dict[str, list[RecordID]] = {
        "tag": [],
        "morpheme": [],
        "sentence": [],
        "passage": [],
    }
    for i in range(size - len(selected)):
        table = ("tag", "morpheme", "sentence", "passage")[i % 4]
        fields: dict[str, Any] = {
            "tag": {"kind": "custom", "name": "Measured tag"},
            "morpheme": {"text": "root", "type": "root"},
            "sentence": {"text": "Example.", "lang": "en", "translation": {}, "source": "fixture"},
            "passage": {"title": "Passage", "text": "Example.", "lang": "en", "source": "fixture"},
        }[table]
        leaves[table].append(select(table, fields, i))
    foreign = node("tag", {"kind": "custom", "name": "Foreign"}, other)
    unselected = node("sense", sense_fields(), None)
    hidden = node("sense", sense_fields(), None)
    memberships.append(
        {
            "start": project,
            "edge": RecordID("includes", uuid4().hex),
            "end": hidden,
            "content": {"owner": user, "hidden": True, "added_at": now},
        }
    )
    for offset in range(0, len(records), 25):
        await checked_query(
            db,
            "FOR $row IN $rows { LET $record = $row.record; LET $content = $row.content; "
            "CREATE $record CONTENT $content; };",
            {"rows": cast(Value, records[offset : offset + 25])},
        )

    edges: list[dict[str, Any]] = []
    expected: list[RecordID] = []
    excluded: list[RecordID] = []

    def edge(
        table: str,
        start: RecordID,
        end: RecordID,
        fields: dict[str, Any] | None = None,
        *,
        owner: RecordID | None = user,
        visible: bool = True,
    ) -> None:
        record = RecordID(table, uuid4().hex)
        content = dict(fields or {})
        if owner is not None:
            content["owner"] = owner
        edges.append({"start": start, "edge": record, "end": end, "content": content})
        (expected if visible else excluded).append(record)

    for i, lexeme in enumerate(lexemes):
        edge("has_lexeme", root, lexeme, owner=user if i % 2 else None)
        if i % 3 == 0:
            edge("contains", root, lexeme, {"position": i})
        if i:
            edge("derives_to", lexemes[i - 1], lexeme, {"via": "fixture"})
    for i, sense in enumerate(senses):
        edge("has_sense", lexemes[i % len(lexemes)], sense, {"rank": i})
        if i:
            edge("relates_to", senses[i - 1], sense, {"type": "synonym", "source": "fixture"})
    for i, tag in enumerate(leaves["tag"]):
        edge("member_of", senses[i % len(senses)], tag, owner=user if i % 2 else None)
    for i, morpheme in enumerate(leaves["morpheme"]):
        edge("composed_of", lexemes[i % len(lexemes)], morpheme, {"order": i})
    for table in ("sentence", "passage"):
        for i, target in enumerate(leaves[table]):
            edge("used_in", senses[i % len(senses)], target)
    for i, (sentence, passage) in enumerate(
        zip(leaves["sentence"], leaves["passage"], strict=False)
    ):
        edge("part_of", sentence, passage, {"order": i})
    edge("has_sense", lexemes[0], unselected, {"rank": 100}, visible=False)
    edge("has_sense", lexemes[0], hidden, {"rank": 101}, visible=False)
    edge("member_of", senses[0], foreign, visible=False)
    edge("has_lexeme", root, lexemes[0], owner=other, visible=False)
    relations = memberships + edges
    for offset in range(0, len(relations), 25):
        await checked_query(
            db,
            "FOR $row IN $rows { LET $start = $row.start; LET $edge = $row.edge; "
            "LET $end = $row.end; LET $content = $row.content; "
            "RELATE $start->$edge->$end CONTENT $content; };",
            {"rows": cast(Value, relations[offset : offset + 25])},
        )
    return Workload(selected, expected, [foreign, unselected, hidden], excluded)


async def edge_query_plans(
    db: AsyncWsSurrealConnection,
    user: RecordID,
    selected: set[RecordID],
    txn: UUID,
    *,
    filtered: bool = False,
) -> dict[str, Any]:
    variables: dict[str, Value] = {
        "user": user,
        "frontier": cast(Value, list(selected)),
        "authorized": cast(Value, list(selected)),
        "direction": "both",
        "induced": True,
        "limit": 10_001,
        "table": "has_lexeme" if filtered else "member_of",
        "relations": cast(Value, ["has_lexeme"] if filtered else list(RELATIONS)),
    }
    legacy = await checked_query(
        db,
        "SELECT * FROM type::table($table) "
        "WHERE (owner = NONE OR owner = $user) AND (in.owner = NONE OR in.owner = $user) "
        "AND (out.owner = NONE OR out.owner = $user) "
        "AND in IN $authorized AND out IN $authorized "
        "AND (($induced AND in IN $frontier AND out IN $frontier) OR "
        "($induced = false AND (($direction != 'incoming' AND in IN $frontier) OR "
        "($direction != 'outgoing' AND out IN $frontier)))) LIMIT $limit EXPLAIN FULL;",
        variables,
        txn_id=txn,
    )
    combined = await checked_query(
        db,
        "SELECT * FROM has_lexeme, has_sense, composed_of, derives_to, relates_to, "
        "member_of, contains, used_in, part_of WHERE record::tb(id) IN $relations "
        "AND (owner = NONE OR owner = $user) AND (in.owner = NONE OR in.owner = $user) "
        "AND (out.owner = NONE OR out.owner = $user) "
        "AND in IN $authorized AND out IN $authorized "
        "AND (($induced AND in IN $frontier AND out IN $frontier) OR "
        "($induced = false AND (($direction != 'incoming' AND in IN $frontier) OR "
        "($direction != 'outgoing' AND out IN $frontier)))) LIMIT $limit EXPLAIN FULL;",
        variables,
        txn_id=txn,
    )
    return {
        "legacy": legacy[0],
        "combined": combined[0],
        "optimized": legacy[0] if filtered else combined[0],
    }
