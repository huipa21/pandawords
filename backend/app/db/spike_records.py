"""N04–N13: IDs, schema constraints, ownership and graph writes."""

from __future__ import annotations

from surrealdb import Null, RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from .spike_support import Finding, first, rejects, schema


async def verify_records(db: AsyncWsSurrealConnection) -> list[Finding]:
    findings: list[Finding] = []
    literal = await first(db, "RETURN lemma:['en', 'run'];")
    constructed = await first(
        db, "RETURN type::record($table, $parts);", {"table": "lemma", "parts": ["en", "run"]}
    )
    assert literal == constructed == RecordID("lemma", ["en", "run"])
    findings.append(Finding("N04", "PASS", "array literal = type::record(table, parts)"))

    lemma = RecordID("lemma", ["en", "run"])
    await db.query("UPSERT $id CONTENT $data;", {"id": lemma, "data": {"text": "run"}})
    rows = await first(db, "SELECT * FROM $id WHERE owner = NONE;", {"id": lemma})
    assert rows[0]["id"] == lemma
    findings.append(Finding("N05", "PASS", "RecordID array bound to UPSERT and decoded unchanged"))

    user = RecordID("user", "alice")
    sense = RecordID("sense", ["en", "run", "verb", 1, "k"])
    nested = RecordID("override", [user, sense])
    value = await first(db, "RETURN $id;", {"id": nested})
    assert value == nested
    assert (
        await first(db, "RETURN override:[user:alice, sense:['en','run','verb',1,'k']];") == nested
    )
    findings.append(Finding("N06", "PASS", "nested RecordIDs round-trip in array ID"))

    await schema(db)
    await schema(db)
    info = await first(db, "INFO FOR TABLE lemma;")
    assert "TYPE string" in info["fields"]["text"]
    assert "SCHEMAFULL" in (await first(db, "INFO FOR DB;"))["tables"]["lemma"]
    findings.append(Finding("N07", "PASS", "IF NOT EXISTS + FIELD OVERWRITE executed twice"))

    lexeme = RecordID("lexeme", "run")
    await db.query(
        "UPSERT $lexeme CONTENT {owner: NONE}; UPSERT $sense CONTENT {owner: NONE};",
        {"lexeme": lexeme, "sense": sense},
    )
    wrong_type = await rejects(
        db,
        "RELATE $a->has_sense->$b SET rank = 1, owner = NONE;",
        {"a": lemma, "b": sense},
    )
    missing = await rejects(
        db,
        "RELATE $a->has_sense->$b SET rank = 1, owner = NONE;",
        {"a": lexeme, "b": RecordID("sense", "missing")},
    )
    assert wrong_type and missing
    findings.append(
        Finding("N08", "PASS", "typed ENFORCED relations reject wrong/missing endpoints")
    )

    rows = await first(db, "SELECT * FROM $id WHERE owner = NONE;", {"id": lemma})
    assert "gloss" not in rows[0]
    null_error = await rejects(db, "UPDATE $id SET gloss = NULL WHERE owner = NONE;", {"id": lemma})
    await db.query("UPDATE $id SET nullable = NULL WHERE owner = NONE;", {"id": lemma})
    values = await first(db, "RETURN [NONE, NULL, type::is_none(NONE), type::is_null(NULL)];")
    assert values[2:] == [True, True] and null_error
    assert values[0] is None and values[1] is Null
    bound = await first(db, "RETURN [$none, $null];", {"none": None, "null": Null})
    assert bound == values[:2]
    findings.append(
        Finding(
            "N09", "PASS", f"NONE={values[0]!r}, NULL={values[1]!r}; option<string> rejects NULL"
        )
    )

    await db.query(
        """
        UPSERT lemma:private_a CONTENT {text: 'owned', owner: $a};
        UPSERT lemma:private_b CONTENT {text: 'other', owner: $b};
        """,
        {"a": user, "b": RecordID("user", "bob")},
    )
    params = {"user": user}
    equals = await first(
        db, "SELECT VALUE id FROM lemma WHERE owner = NONE OR owner = $user;", params
    )
    is_none = await first(
        db, "SELECT VALUE id FROM lemma WHERE owner IS NONE OR owner = $user;", params
    )
    assert equals == is_none
    assert lemma in equals and RecordID("lemma", "private_a") in equals
    assert RecordID("lemma", "private_b") not in equals
    findings.append(
        Finding("N10", "PASS", "both NONE predicates include shared/own, exclude other")
    )

    await db.query(
        "UPSERT $id CONTENT $data; UPSERT $id MERGE {gloss: 'move fast'};",
        {"id": lemma, "data": {"text": "run", "owner": None}},
    )
    row = (await first(db, "SELECT * FROM $id WHERE owner = NONE;", {"id": lemma}))[0]
    assert row["text"] == "run" and row["gloss"] == "move fast"
    findings.append(Finding("N11", "PASS", "CONTENT creates/replaces; MERGE preserves text"))

    edges = await first(
        db,
        "RELATE $a->has_sense->$b SET rank = $rank, owner = NONE;",
        {"a": lexeme, "b": sense, "rank": 2},
    )
    assert edges[0]["in"] == lexeme and edges[0]["out"] == sense and edges[0]["rank"] == 2
    findings.append(Finding("N12", "PASS", "RELATE bound endpoints and rank returns edge"))

    await db.query("DEFINE INDEX IF NOT EXISTS uniq ON has_sense FIELDS in, out UNIQUE;")
    duplicate = await rejects(
        db,
        "RELATE $a->has_sense->$b SET rank = 3, owner = NONE;",
        {"a": lexeme, "b": sense},
    )
    assert "uniq" in duplicate
    findings.append(Finding("N13", "PASS", "unique(in,out) rejects duplicate edge"))
    return findings
