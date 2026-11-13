# SurrealDB 3.3 notes

Check here before writing SurrealQL. **Status:** ✅ verified on the version shown · ❌ original
form is wrong (a working, verified replacement is given). New, unverified beliefs must be
tested before being used.

Task **1.3.2** verified all 23 notes on **2026-11-14**, against the **test** instance on
loopback port **8101**, Python **3.14.3**, and Python SDK **`surrealdb==3.0.0`**. The official
image was `docker.io/surrealdb/surrealdb:v3.3.5`, digest
`sha256:3db515b88e79737aa828c05fbf1515748004ba57495ff89a013851cc3f1ad4b9`,
running `start --no-banner --log warn memory`. Both HTTP `/version` and SDK `version()`
reported `surrealdb-3.3.5`.

Run the retained regression aid from the repository root, with the shared test server
already running:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\verify_surreal.py
```

It reads credentials only through `Settings`, prints no credentials, requires a loopback
WebSocket `/rpc` URL on port 8101, and allocates random namespace/database names. It verifies
backup restoration in a second generated database, removes **only those two databases** in
`finally`, checks their absence, and leaves the shared server running. It never uses the
configured dev namespace/database. An empty generated namespace may remain; namespace-wide
deletion is deliberately not used. All executable SurrealQL is in `backend/app/db/spike*.py`;
the script only imports the runner. Assertions are the checks: run without Python `-O`.

| # | Topic | Belief / snippet | Status | Verified on | Note |
|---|---|---|---|---|---|
| N01 | Server start | `surreal start --no-banner --log warn memory`; `/health`, `/version` | ✅ | 3.3.5 / SDK 3.0.0 | Official image/command inspected; `/health` returns 200. This run exercises memory, not RocksDB persistence. Credentials come from container environment, not literal passwords in commands. |
| N02 | Python SDK connect | `AsyncSurreal(url)` → `connect()` → `signin({"username": ..., "password": ...})` → `use(ns, db)` | ✅ | 3.3.5 / SDK 3.0.0 | Async context manager closes the connection; explicit `connect()` is safe inside it. Use IPv4 loopback on this Windows/Podman setup (see below). |
| N03 | Query + params | `await db.query(sql, params)` returns **one result per statement** | ✅ | 3.3.5 / SDK 3.0.0 | `RETURN 1` → `[1]`; two RETURNs → `["run", 2]`; SELECT → `[rows]`. `.first()` unwraps one statement. `query_raw()` retains per-statement status/error envelopes. `query()` raises on THROW. |
| N04 | Array record IDs | `lemma:['en','run']`; `type::record($table, $parts)` | ✅ | 3.3.5 / SDK 3.0.0 | Both produce the same array ID. No reliance on the old `type::thing` name. |
| N05 | RecordID in Python | `RecordID("lemma", ["en","run"])` | ✅ | 3.3.5 / SDK 3.0.0 | Bound to UPSERT and SELECT; decoded ID compares equal. |
| N06 | Record inside array ID | `override:[user:alice, sense:['en','run','verb',1,'k']]` | ✅ | 3.3.5 / SDK 3.0.0 | Literal equals the nested Python RecordID; bound parameter round-trips unchanged. |
| N07 | Idempotent DDL | `DEFINE TABLE IF NOT EXISTS lemma SCHEMAFULL; DEFINE FIELD OVERWRITE text ON lemma TYPE string;` | ✅ | 3.3.5 / SDK 3.0.0 | Schema DDL runs twice; INFO confirms SCHEMAFULL and string field. |
| N08 | Relation tables | `DEFINE TABLE has_sense TYPE RELATION IN lexeme OUT sense ENFORCED SCHEMAFULL;` | ✅ | 3.3.5 / SDK 3.0.0 | Valid edges succeed; wrong endpoint table and nonexistent endpoint are both rejected. ENFORCED goes before SCHEMAFULL. |
| N09 | Optional fields | `TYPE option<string>`; `TYPE option<string \| null>` | ✅ | 3.3.5 / SDK 3.0.0 | NONE is absent/decoded `None`; NULL is SDK `Null` singleton. `option<string>` rejects NULL; the union accepts it. Python `None` and `Null` bind distinctly. Predicates are `type::is_none` / `type::is_null`, **not** `type::is::none` / `type::is::null`. |
| N10 | Owner filter | `WHERE owner = NONE OR owner = $user`; `owner IS NONE` also works | ✅ | 3.3.5 / SDK 3.0.0 | Both predicates return shared + Alice rows and exclude Bob's row. |
| N11 | Upsert | `UPSERT $id CONTENT $data; UPSERT $id MERGE {gloss: 'move fast'};` | ✅ | 3.3.5 / SDK 3.0.0 | CONTENT creates/replaces; MERGE preserves the existing text. |
| N12 | RELATE + fields | `RELATE $a->has_sense->$b SET rank = $rank, owner = NONE;` | ✅ | 3.3.5 / SDK 3.0.0 | Returned edge has bound in/out/rank. |
| N13 | Unique edge | `DEFINE INDEX IF NOT EXISTS uniq ON has_sense FIELDS in, out UNIQUE;` | ✅ | 3.3.5 / SDK 3.0.0 | Duplicate RELATE fails naming index `uniq`. |
| N14 | Traversal | `SELECT ->has_lexeme->lexeme->has_sense->sense.* AS senses FROM $lemma WHERE owner = NONE;` | ✅ | 3.3.5 / SDK 3.0.0 | Returns projected sense records through both edges. For mixed ownership, filter each traversed relation/target too; the fixture graph here is entirely shared. |
| N15 | Recursive traversal | `RETURN $rec.{1..3}->relates_to->sense;` | ✅ | 3.3.5 / SDK 3.0.0 | On a five-node chain, returns node 4 (three hops), not node 5 or a flat union of all intermediate nodes. `{1..1}` returns node 2. |
| N16 | Transactions | `BEGIN TRANSACTION; ... COMMIT TRANSACTION;` including DEFINE | ✅ | 3.3.5 / SDK 3.0.0 | DEFINE TABLE + FIELD + CREATE + THROW leaves no table; the success variant commits it. Migration runners must inspect errors, not mistake an RPC response for success. |
| N17 | SDK transactions | Original no-argument `commit()` / `cancel()` | ❌ | 3.3.5 / SDK 3.0.0 | Working replacement: `txn = await db.begin()`; `query(..., txn_id=txn)`; `await db.commit(txn)` or `await db.cancel(txn)`. Committed row persists; cancelled row is absent. |
| N18 | LIVE queries | `LIVE SELECT * FROM job WHERE status = 'queued' AND owner = NONE;` | ✅ | 3.3.5 / SDK 3.0.0 | Await `subscribe_live(id)` to obtain the async generator. CREATE notification identifies the queued shared row; done/other-owner writes are excluded. Kill the query and close the generator in finally. |
| N19 | Datetimes | tz-aware Python `datetime`; `time::now()` | ✅ | 3.3.5 / SDK 3.0.0 | Decodes as SDK `PreciseDatetime` (a `datetime` subclass), UTC-aware; microseconds match and nanosecond remainder survives read/rebind. |
| N20 | Schema info | `INFO FOR DB; INFO FOR TABLE $table;` | ✅ | 3.3.5 / SDK 3.0.0 | Include DB definitions **and each table's fields/indexes**; sorted JSON is identical across repeated reads. Bound table name works. See `snapshot()` below. |
| N21 | Export / import | `await db.export()` / `await db.import_(sql)` | ✅ | 3.3.5 / SDK 3.0.0 | SDK calls HTTP `/export` and `/import` even from a WS connection. Export begins with `OPTION IMPORT;`. Restore into a separate empty generated DB reproduces the complete schema and records/edges in every table. This is the verified backup path for 1.6.4; CLI export/import was not exercised. |
| N22 | Search | `FULLTEXT ANALYZER word_tokens BM25`; `string::starts_with(text, $prefix)` | ✅ | 3.3.5 / SDK 3.0.0 | lowercase analyzer matches `RUN` to `run`; prefix `ru` matches `run`. Prefix predicate is not a claim of index acceleration; SQLite remains the lexicon search backend. |
| N23 | Remove database | `REMOVE DATABASE IF EXISTS $database;` | ✅ | 3.3.5 / SDK 3.0.0 | Bound generated DB name; executing twice succeeds; `INFO FOR NS` confirms original and restore DBs absent. No identifier interpolation or namespace deletion needed. |

## Verified snippets

Task **1.5.1**, **2026-11-14**, reverified auth DDL on the loopback **test** server (8101),
reporting **surrealdb-3.3.5**, with SDK **3.0.0**. `0002_auth.surql` and
`tests/integration/test_auth_schema.py` verify literal string unions (`'admin' | 'user'`,
theme and accent), SCHEMAFULL nested object fields, required booleans, typed `record<user>`
and `option<record<refresh_token>>`, optional datetimes, and unique username/hash indexes.
Duplicate writes fail naming their unique index; wrong role/theme/accent/reference table and
string expiry/boolean values are rejected. UTC expiry/revocation datetimes and replacement
record IDs round-trip. All writes use fresh harness databases, removed individually on teardown;
the dev database is untouched. The snapshot runner captures the accepted field/index definitions.

All snippets below target **server 3.3.5 / Python SDK 3.0.0**. Executable versions live in
`app.db.spike_support`, `spike_records`, `spike_graph`, and `spike_operations`; do not move
SurrealQL into scripts, API handlers, or services.

### Connection and result shape (N02, N03)

Run Python snippets with `backend` as the working directory. Credentials are read from
`Settings`; never print settings or authentication payloads.

```python
import asyncio

from surrealdb import AsyncSurreal
from app.core.config import Settings

async def main():
    settings = Settings()
    async with AsyncSurreal("ws://127.0.0.1:8101/rpc") as db:
        await db.connect()
        await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
        await db.use("your_isolated_namespace", "your_isolated_database")
        assert await db.query("RETURN $text; RETURN 2;", {"text": "run"}) == ["run", 2]
        assert await db.query("RETURN 1;").first() == 1

asyncio.run(main())
```

On this Windows/Podman host, HTTP health worked with `localhost` but SDK WebSocket
handshakes timed out; `127.0.0.1` worked with the same credentials/server. The spike maps
`localhost` to IPv4 and preserves explicitly configured IPv6 loopback.

Companion lifecycle evidence from task 1.3.1:
`tests/integration/test_readiness.py::test_sdk_reconnects_the_same_connection_after_socket_loss`
closes only its own socket and verifies `/readyz` recovers using the same SDK object.
`ReconnectOptions(attempts=-1)` recovers established socket connections; the companion test
checks query readiness on the same connection object.
Initial connection failure still needs an application retry loop (covered by
`tests/unit/test_database.py::test_initial_connection_retries_and_closes_without_logging_secrets`);
startup health must not wait indefinitely for the initial database connection.

### IDs, optional values and owner filtering (N04–N06, N09, N10)

```python
from surrealdb import Null, RecordID

lemma = RecordID("lemma", ["en", "run"])
sense = RecordID("sense", ["en", "run", "verb", 1, "k"])
override = RecordID("override", [RecordID("user", "alice"), sense])
# In an authenticated async connection:
assert await db.query("RETURN $id;", {"id": override}) == [override]
assert await db.query("RETURN [$none, $null];", {"none": None, "null": Null}) == [[None, Null]]
```

```surql
RETURN type::record($table, $parts);
DEFINE FIELD OVERWRITE gloss ON lemma TYPE option<string>;
DEFINE FIELD OVERWRITE nullable ON lemma TYPE option<string | null>;
SELECT * FROM lemma WHERE owner = NONE OR owner = $user;
```

### Idempotent schema, relations and graph reads (N07, N08, N11–N15)

```surql
DEFINE TABLE IF NOT EXISTS lemma SCHEMAFULL;
DEFINE FIELD OVERWRITE text ON lemma TYPE string;
DEFINE FIELD OVERWRITE owner ON lemma TYPE option<record<user>>;
DEFINE TABLE IF NOT EXISTS lexeme SCHEMAFULL;
DEFINE TABLE IF NOT EXISTS sense SCHEMAFULL;
DEFINE TABLE IF NOT EXISTS has_sense
    TYPE RELATION IN lexeme OUT sense ENFORCED SCHEMAFULL;
DEFINE FIELD OVERWRITE rank ON has_sense TYPE int;
DEFINE FIELD OVERWRITE owner ON has_sense TYPE option<record<user>>;
DEFINE INDEX IF NOT EXISTS uniq ON has_sense FIELDS in, out UNIQUE;
UPSERT $id CONTENT $data;
UPSERT $id MERGE {gloss: 'move fast'};
RELATE $a->has_sense->$b SET rank = $rank, owner = NONE;
```

The last MERGE assumes the N09 `gloss` field has been defined. The complete shared-graph
fixture (including `has_lexeme` and `relates_to`) is in `spike_support.schema()`.
For that fixture:

```surql
SELECT ->has_lexeme->lexeme->has_sense->sense.* AS senses
FROM $lemma WHERE owner = NONE;
RETURN $rec.{1..3}->relates_to->sense;
```

These are shared-data traversal examples, **not** authorization-complete queries for
graphs with mixed owners. N10 independently verifies cross-user filtering.

### Migration rollback and SDK transactions (N16, N17)

```surql
BEGIN TRANSACTION;
DEFINE TABLE rollback_probe SCHEMAFULL;
DEFINE FIELD text ON rollback_probe TYPE string;
CREATE rollback_probe:row SET text = 'must disappear';
THROW 'spike_rollback';
COMMIT TRANSACTION;
```

`query_raw()` returns statement statuses including ERR; the table must not appear in
`INFO FOR DB`. Omitting THROW (with a different probe table name) commits the schema/data.
The migration runner can wrap schema and its migration marker in the same transaction.

```python
txn = await db.begin()
try:
    await db.query("UPSERT job:example CONTENT {status: 'queued'};", txn_id=txn)
except BaseException:
    await db.cancel(txn)
    raise
else:
    await db.commit(txn)
```

### LIVE subscriptions and datetimes (N18, N19)

```python
import asyncio
from datetime import UTC, datetime

live_id = await db.query(
    "LIVE SELECT * FROM job WHERE status = 'queued' AND owner = NONE;"
).first()
notifications = await db.subscribe_live(live_id)
try:
    # A separate writer can now enqueue a job.
    notification = await asyncio.wait_for(anext(notifications), timeout=5)
finally:
    await db.kill(live_id)
    await notifications.aclose()

instant = datetime(2026, 11, 13, 16, 0, 0, 123456, tzinfo=UTC)
assert await db.query("RETURN $instant;", {"instant": instant}) == [instant]
```

The spike uses its own writer and additionally checks status/owner exclusions.
SDK `PreciseDatetime.nanosecond` stores the sub-microsecond remainder (0–999); ordinary
`datetime` arithmetic does not promise to preserve that extra remainder.

### Schema snapshot, backup and exact cleanup (N20, N21, N23)

`spike_operations.snapshot(db)` obtains `INFO FOR DB`, iterates its sorted table names with
`INFO FOR TABLE $table`, and serializes both using `json.dumps(..., sort_keys=True, indent=2)`.
Do not snapshot only `INFO FOR DB`: field and index definitions live in the table info.
The spike checks two identical snapshots, and compares schema plus all synthetic table
records after restoring:

```python
exported = await db.export()  # HTTP export, using existing SDK authentication.
await db.use(isolated_namespace, empty_restore_database)
await db.import_(exported)  # Keep the exported OPTION IMPORT; header.
# Inspect and compare restored schema/data before removing either database.
await db.query(
    "REMOVE DATABASE IF EXISTS $database;", {"database": empty_restore_database}
)
await db.use(isolated_namespace, original_database)
await db.query("REMOVE DATABASE IF EXISTS $database;", {"database": original_database})
```

The regression aid keeps the export in memory. It does not create backup files or prove
CLI behavior. Task 1.6.4 can use this verified SDK HTTP path; backup file rotation and
disaster-recovery procedures remain that task's responsibility.

### Full-text and prefix search (N22)

```surql
DEFINE ANALYZER IF NOT EXISTS word_tokens TOKENIZERS blank, class FILTERS lowercase;
DEFINE INDEX IF NOT EXISTS lemma_search ON lemma FIELDS text
    FULLTEXT ANALYZER word_tokens BM25;
SELECT VALUE text FROM lemma WHERE owner = NONE AND text @@ $term;
SELECT VALUE text FROM lemma
WHERE owner = NONE AND string::starts_with(text, $prefix);
```
