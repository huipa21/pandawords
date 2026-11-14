from typing import Any
from uuid import uuid4

from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import encode_rid
from app.db import dictionary_schema_test_support as schema
from app.domain.identity import user_key
from app.services import jobs
from app.worker.runtime import execute


async def target(
    db: AsyncWsSurrealConnection, table: str = "sense", owner: str | None = None
) -> dict[str, str]:
    attributes: dict[str, Any] = {
        "lemma": {
            "text": uuid4().hex,
            "lang": "en",
            "kind": "word",
            "freq_zipf": 3,
            "exam_tags": [],
            "source": "test",
        },
        "lexeme": {"pos": "verb", "forms": [], "pron": [], "etymology_no": 0},
        "sense": {
            "definition": "Move quickly " + uuid4().hex,
            "gloss": {"zh": "跑"},
            "register": [],
            "domain": [],
            "examples": [],
            "rank": 0,
            "common": True,
            "source": "test",
        },
    }[table]
    record = RecordID(table, uuid4().hex)
    attributes["owner"] = RecordID("user", user_key(owner)) if owner else None
    await schema.create(db, record, attributes)
    return {"target_table": table, "target_id": encode_rid(record, table)}


async def finish(db: AsyncWsSurrealConnection, settings: Settings, id: str) -> None:
    for _ in range(100):
        job = await jobs.claim(db)
        assert job is not None
        if job.id == id:
            await execute(db, job, settings=settings)
            return
        await jobs.complete(db, job)
    raise AssertionError("Missing mnemonic job")
