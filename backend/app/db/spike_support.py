"""Shared assertions for the disposable SurrealDB regression spike."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from surrealdb.connections.async_ws import AsyncWsSurrealConnection


@dataclass(frozen=True)
class Finding:
    note: str
    status: str
    evidence: str


async def first(
    db: AsyncWsSurrealConnection, sql: str, params: dict[str, Any] | None = None
) -> Any:
    results = await db.query(sql, params)
    assert len(results) == 1, results
    return results[0]


async def rejects(
    db: AsyncWsSurrealConnection, sql: str, params: dict[str, Any] | None = None
) -> str:
    response = await db.query_raw(sql, params)
    failures = [r["result"] for r in response["result"] if r["status"] == "ERR"]
    assert failures, response
    return str(failures[0])


async def schema(db: AsyncWsSurrealConnection) -> None:
    await db.query("""
        DEFINE TABLE IF NOT EXISTS lemma SCHEMAFULL;
        DEFINE FIELD OVERWRITE text ON lemma TYPE string;
        DEFINE FIELD OVERWRITE owner ON lemma TYPE option<record<user>>;
        DEFINE FIELD OVERWRITE gloss ON lemma TYPE option<string>;
        DEFINE FIELD OVERWRITE nullable ON lemma TYPE option<string | null>;
        DEFINE FIELD OVERWRITE seen ON lemma TYPE option<datetime>;
        DEFINE TABLE IF NOT EXISTS lexeme SCHEMAFULL;
        DEFINE FIELD OVERWRITE owner ON lexeme TYPE option<record<user>>;
        DEFINE TABLE IF NOT EXISTS sense SCHEMAFULL;
        DEFINE FIELD OVERWRITE owner ON sense TYPE option<record<user>>;
        DEFINE TABLE IF NOT EXISTS has_lexeme
            TYPE RELATION IN lemma OUT lexeme ENFORCED SCHEMAFULL;
        DEFINE FIELD OVERWRITE owner ON has_lexeme TYPE option<record<user>>;
        DEFINE TABLE IF NOT EXISTS has_sense
            TYPE RELATION IN lexeme OUT sense ENFORCED SCHEMAFULL;
        DEFINE FIELD OVERWRITE owner ON has_sense TYPE option<record<user>>;
        DEFINE FIELD OVERWRITE rank ON has_sense TYPE int;
        DEFINE TABLE IF NOT EXISTS relates_to
            TYPE RELATION IN sense OUT sense ENFORCED SCHEMAFULL;
        DEFINE FIELD OVERWRITE owner ON relates_to TYPE option<record<user>>;
        DEFINE TABLE IF NOT EXISTS job SCHEMAFULL;
        DEFINE FIELD OVERWRITE owner ON job TYPE option<record<user>>;
        DEFINE FIELD OVERWRITE status ON job TYPE string;
    """)
