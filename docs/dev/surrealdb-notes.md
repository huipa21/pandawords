# SurrealDB 3.3 notes

Check here before writing SurrealQL. **Status:** ✅ verified on the version shown · ❓ unverified
belief (verify before relying on it) · ❌ wrong (the correct form is in the note).

Verification happens in task **1.3.2** against the dev DB. Add new findings whenever something
surprises you.

| # | Topic | Belief / snippet | Status | Verified on | Note |
|---|---|---|---|---|---|
| N01 | Server start | `surreal start --user root --pass root rocksdb:/data/db` (dev), `memory` (test); `/health` endpoint | ❓ | | |
| N02 | Python SDK connect | `AsyncSurreal(url)` → `connect()` → `signin({"username","password"})` → `use(ns, db)`; context manager supported | ❓ | | SDK `surrealdb` 3.0.0 |
| N03 | Query + params | `await db.query("SELECT * FROM lemma WHERE text = $t", {"t": "run"})` — result shape (list per statement?) | ❓ | | |
| N04 | Array record IDs | `lemma:['en', 'run']` literal; build from parts with `type::record('lemma', ['en','run'])` (was `type::thing` in ≤2.x?) | ❓ | | |
| N05 | RecordID in Python | `RecordID('lemma', ['en','run'])` round-trips via params and results | ❓ | | |
| N06 | Record inside array ID | `override:[user:abc, sense:['en','run','verb',1,'k']]` | ❓ | | |
| N07 | Idempotent DDL | `DEFINE TABLE IF NOT EXISTS lemma SCHEMAFULL;` `DEFINE FIELD OVERWRITE text ON lemma TYPE string;` | ❓ | | |
| N08 | Relation tables | `DEFINE TABLE has_sense TYPE RELATION IN lexeme OUT sense SCHEMAFULL;` (`ENFORCED` option?) | ❓ | | |
| N09 | Optional fields | `TYPE option<string>`; NONE vs NULL semantics; SDK decoding of NULL/NONE | ❓ | | SDK 3.0 changed NULL decoding |
| N10 | Owner filter | `WHERE owner = NONE OR owner = $user` vs `owner IS NONE` | ❓ | | |
| N11 | Upsert | `UPSERT $id CONTENT {...}` / `UPSERT $id MERGE {...}` | ❓ | | |
| N12 | RELATE + fields | `RELATE $a->has_sense->$b SET rank = $r, owner = NONE;` | ❓ | | |
| N13 | Unique edge | `DEFINE INDEX uniq ON has_sense FIELDS in, out UNIQUE;` prevents duplicate edges | ❓ | | |
| N14 | Traversal | `SELECT ->has_lexeme->lexeme->has_sense->sense.* AS senses FROM $lemma` | ❓ | | |
| N15 | Recursive traversal | `$rec.{1..3}->relates_to->sense` | ❓ | | |
| N16 | Transactions | `BEGIN TRANSACTION; ... COMMIT TRANSACTION;` with DEFINE statements rolls back fully on error | ❓ | | needed by the migration runner |
| N17 | SDK transactions | WebSocket-only `begin()/commit()/cancel()` session API | ❓ | | |
| N18 | LIVE queries | `LIVE SELECT * FROM job WHERE status = 'queued'` via the SDK subscribe API | ❓ | | worker wakeup |
| N19 | Datetimes | Python tz-aware `datetime` ↔ SurrealDB `datetime`; `time::now()` | ❓ | | |
| N20 | Schema info | `INFO FOR DB` / `INFO FOR TABLE x` output is stable enough to snapshot (sorted keys) | ❓ | | |
| N21 | Export / import | `surreal export --endpoint … --namespace … --database … out.surql`; HTTP `/export`; `surreal import` | ❓ | | site backup |
| N22 | Search | Prefix / full-text search on `lemma.text` (`DEFINE ANALYZER`, `FULLTEXT`/`SEARCH` index syntax in 3.x) | ❓ | | lexicon search is in SQLite; this is for the user's own words |
| N23 | Remove database | `REMOVE DATABASE IF EXISTS t_xxx;` from the SDK, for test cleanup | ❓ | | |

## Verified snippets

Add copy-paste-ready snippets here once ✅ (with the verified version).
