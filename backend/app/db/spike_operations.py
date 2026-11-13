"""N20–N23: deterministic schema snapshots, backup, search and cleanup."""

from __future__ import annotations

import json
from typing import Any

from surrealdb import RecordID, Table
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from .spike_support import Finding, first


async def snapshot(db: AsyncWsSurrealConnection) -> str:
    database = await first(db, "INFO FOR DB;")
    tables = {}
    for table in sorted(database["tables"]):
        tables[table] = await first(db, "INFO FOR TABLE $table;", {"table": table})
    return json.dumps({"database": database, "tables": tables}, sort_keys=True, indent=2)


async def records(db: AsyncWsSurrealConnection) -> dict[str, Any]:
    tables = (await first(db, "INFO FOR DB;"))["tables"]
    result = {}
    for table in sorted(tables):
        result[table] = await first(
            db,
            "SELECT * FROM $table WHERE owner = NONE OR owner IN $users ORDER BY id;",
            {
                "table": Table(table),
                "users": [RecordID("user", "alice"), RecordID("user", "bob")],
            },
        )
    return result


async def verify_operations(
    db: AsyncWsSurrealConnection, namespace: str, database: str
) -> list[Finding]:
    findings: list[Finding] = []
    before = await snapshot(db)
    assert before == await snapshot(db)
    decoded = json.loads(before)
    assert "fields" in decoded["tables"]["lemma"]
    assert "uniq" in decoded["tables"]["has_sense"]["indexes"]
    findings.append(Finding("N20", "PASS", "DB + all TABLE info sorted into stable JSON twice"))

    # Export/import is HTTP even on an SDK WebSocket connection. Never write backup data to disk.
    original_records = await records(db)
    exported = await db.export()
    assert "OPTION IMPORT" in exported and "DEFINE TABLE" in exported
    restored_database = database + "_restore"
    await db.use(namespace, restored_database)
    try:
        await db.import_(exported)
        assert await snapshot(db) == before
        assert await records(db) == original_records
    finally:
        await db.query("REMOVE DATABASE IF EXISTS $database;", {"database": restored_database})
        await db.use(namespace, database)
    findings.append(
        Finding("N21", "PASS", "SDK HTTP /export + /import restores schema and records")
    )

    await db.query("""
        DEFINE ANALYZER IF NOT EXISTS word_tokens TOKENIZERS blank, class FILTERS lowercase;
        DEFINE INDEX IF NOT EXISTS lemma_search ON lemma FIELDS text
            FULLTEXT ANALYZER word_tokens BM25;
    """)
    fulltext = await first(
        db,
        "SELECT VALUE text FROM lemma WHERE owner = NONE AND text @@ $term;",
        {"term": "RUN"},
    )
    prefix = await first(
        db,
        "SELECT VALUE text FROM lemma WHERE owner = NONE AND string::starts_with(text, $prefix);",
        {"prefix": "ru"},
    )
    assert "run" in fulltext and "run" in prefix
    findings.append(Finding("N22", "PASS", "FULLTEXT analyzer is case-insensitive; prefix matches"))

    await db.query("REMOVE DATABASE IF EXISTS $database;", {"database": database})
    await db.query("REMOVE DATABASE IF EXISTS $database;", {"database": database})
    info = await first(db, "INFO FOR NS;")
    assert database not in info["databases"] and restored_database not in info["databases"]
    findings.append(
        Finding("N23", "PASS", "bound REMOVE DATABASE IF EXISTS twice; INFO confirms absent")
    )
    return findings
