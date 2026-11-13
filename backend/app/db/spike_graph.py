"""N14–N19: traversal, rollback, SDK transactions, LIVE and datetimes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from .spike_support import Finding, first, rejects


async def verify_graph(db: AsyncWsSurrealConnection) -> list[Finding]:
    findings: list[Finding] = []
    lemma = RecordID("lemma", ["en", "run"])
    lexeme = RecordID("lexeme", "run")
    sense = RecordID("sense", ["en", "run", "verb", 1, "k"])
    await db.query("RELATE $a->has_lexeme->$b SET owner = NONE;", {"a": lemma, "b": lexeme})
    traversal = await first(
        db,
        """
        SELECT ->has_lexeme->lexeme->has_sense->sense.* AS senses
        FROM $lemma WHERE owner = NONE;
        """,
        {"lemma": lemma},
    )
    assert traversal[0]["senses"][0]["id"] == sense
    findings.append(Finding("N14", "PASS", "two-hop traversal projects sense records"))

    await db.query(
        """
        UPSERT sense:two CONTENT {owner: NONE};
        UPSERT sense:three CONTENT {owner: NONE};
        UPSERT sense:four CONTENT {owner: NONE};
        UPSERT sense:five CONTENT {owner: NONE};
        RELATE $one->relates_to->sense:two SET owner = NONE;
        RELATE sense:two->relates_to->sense:three SET owner = NONE;
        RELATE sense:three->relates_to->sense:four SET owner = NONE;
        RELATE sense:four->relates_to->sense:five SET owner = NONE;
    """,
        {"one": sense},
    )
    recursive = await first(db, "RETURN $rec.{1..3}->relates_to->sense;", {"rec": sense})
    assert recursive == [RecordID("sense", "four")]
    assert await first(db, "RETURN $rec.{1..1}->relates_to->sense;", {"rec": sense}) == [
        RecordID("sense", "two")
    ]
    findings.append(
        Finding("N15", "PASS", "bounded recursion stops at hop 3, not beyond or all hops")
    )

    error = await rejects(
        db,
        """
        BEGIN TRANSACTION;
        DEFINE TABLE rollback_probe SCHEMAFULL;
        DEFINE FIELD text ON rollback_probe TYPE string;
        CREATE rollback_probe:row SET text = 'must disappear';
        THROW 'spike_rollback';
        COMMIT TRANSACTION;
    """,
    )
    assert error
    info = await first(db, "INFO FOR DB;")
    assert "rollback_probe" not in info["tables"]
    await db.query("""
        BEGIN TRANSACTION;
        DEFINE TABLE committed_probe SCHEMAFULL;
        DEFINE FIELD text ON committed_probe TYPE string;
        CREATE committed_probe:row SET text = 'committed';
        COMMIT TRANSACTION;
    """)
    assert "committed_probe" in (await first(db, "INFO FOR DB;"))["tables"]
    findings.append(Finding("N16", "PASS", "DDL+DML error fully rolls back; success commits"))

    txn = await db.begin()
    await db.query("UPSERT job:cancelled CONTENT {status: 'queued'};", txn_id=txn)
    await db.cancel(txn)
    assert await first(db, "SELECT * FROM job:cancelled WHERE owner = NONE;") == []
    txn = await db.begin()
    await db.query("UPSERT job:committed CONTENT {status: 'done'};", txn_id=txn)
    await db.commit(txn)
    assert len(await first(db, "SELECT * FROM job:committed WHERE owner = NONE;")) == 1
    findings.append(
        Finding("N17", "PASS", "begin returns UUID; query(txn_id=); cancel/commit verified")
    )

    live_id = await first(db, "LIVE SELECT * FROM job WHERE status = 'queued' AND owner = NONE;")
    notifications = await db.subscribe_live(live_id)
    pending = asyncio.create_task(anext(notifications))
    try:
        await db.query("""
            UPSERT job:ignored_status CONTENT {status: 'done'};
            UPSERT job:ignored_owner CONTENT {status: 'queued', owner: user:bob};
        """)
        await db.query("UPSERT job:wakeup CONTENT {status: 'queued'};")
        notification = await asyncio.wait_for(pending, timeout=5)
        assert notification["action"] == "CREATE"
        result = notification["result"]
        assert isinstance(result, dict)
        assert result["id"] == RecordID("job", "wakeup")
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await db.kill(live_id)
        await notifications.aclose()
    findings.append(
        Finding("N18", "PASS", "filtered LIVE query delivers CREATE; subscription killed")
    )

    now = datetime(2026, 11, 13, 16, 0, 0, 123456, tzinfo=UTC)
    await db.query("UPDATE $id SET seen = $now WHERE owner = NONE;", {"id": lemma, "now": now})
    result = await first(
        db, "SELECT seen, time::now() AS server_now FROM $id WHERE owner = NONE;", {"id": lemma}
    )
    seen = result[0]["seen"]
    assert seen == now
    assert result[0]["server_now"].tzinfo is not None
    precise = await first(db, "RETURN d'2026-11-13T16:00:00.123456789Z';")
    assert precise.microsecond == 123456 and precise.nanosecond == 789
    rebound = await first(db, "RETURN $instant;", {"instant": precise})
    assert rebound.nanosecond == 789
    findings.append(Finding("N19", "PASS", f"{type(seen).__name__} preserves UTC + nanoseconds"))
    return findings
