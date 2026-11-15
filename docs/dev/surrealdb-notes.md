# SurrealDB 3.3 notes

## Personal semantic relation identities (4.4.3) ✅

Verified with the existing isolated loopback 8101 SurrealDB 3.3 harness:
bound deterministic edge records in `RELATE $start->$edge->$end SET ...` and
insert-only SDK transactions serialize four concurrent identical creates to one 201
and three explicit 200 duplicates using the existing `_atomic` conflict retry.
Including the owner in the primary identity keeps two legitimate users' identical
endpoint/type links independent. Existing shared or foreign identity collisions fail
closed before RELATE; DELETE rechecks the owner and both current endpoint owners and
selection visibility. Ordered LIMIT/START pagination and effective label batches reuse
the graph authorization snapshot. Retained probes: `tests/api/test_relations.py`.
The existing 0005 relation fields suffice; no migration or persistent dev data change.

## Scoped graph seed discovery (4.4.2) ✅

Visible selected senses also authorize their implicit lexeme/lemma ancestors, even without
lexeme `includes` markers (the normal add API writes only lemma and selected-sense markers).
A hidden selection cannot authorize these ancestors; project-local hidden ancestry still
wins. The real-database graph regression covers depth-1 lexemes and depth-2 selected senses.

Verified against the throwaway 8101 instance by `tests/api/test_graph.py`:
binding optional project IDs in `($project = NONE OR in = $project)` preserves global
project-union visibility and restricts project discovery when supplied. Project ownership is
checked separately in the same transaction. Hidden lemma ancestry removes shared selected
senses; owned global tags remain discoverable, and a second user's project discovery is 404.
Seed batches reuse existing effective-node/override queries (maximum 300 per batch).

## Review media defaults and partial preferences (5.1.3) ✅

Verified against the existing isolated **8101** SurrealDB 3.3 harness: after defining two
non-optional bool fields, updating only the first missing field on a legacy user fails because
the second still contains NONE. Backfill both fields in **one** UPDATE, using
`IF prefs.field = NONE THEN true ELSE prefs.field END` for each, to preserve existing false
values. Replaying the migration retains false toggles and every other preference.
Bound `IF $flag THEN $value ELSE prefs.field END` assignments support atomic owner-filtered
partial preference updates without replacing the object. Focused API/migration tests verify
each toggle, accent, isolation and preservation of theme/locale/retention. No 8100 migration or
service lifecycle operation was performed by this task branch.

## Containing-phrase traversal (4.1.2) ✅

Verified against the existing isolated random-database harness on loopback **8101**,
SurrealDB **3.3.5**: `SELECT VALUE <-(contains WHERE ...).in FROM $targets` returns
per-component arrays; `array::flatten((SELECT VALUE ...))` can feed an outer
`lemma WHERE id IN ...` query. The outer selection deduplicates repeated component edges
before `ORDER BY text ASC, id ASC LIMIT $limit START $offset`. Bound integer pagination
parameters work. Relation `owner`, `in.owner`, `out.owner` and source-record owner checks
independently exclude foreign edges/endpoints; lemma ancestry checks `has_lexeme` as well.
The regression is `tests/api/test_phrases.py`; no new migration or schema is needed.

### Private reading transactions (4.2.2) ✅

Verified against the existing isolated 8101 SurrealDB 3.3 test server:
bound `SELECT * FROM type::table($table) ... LIMIT $limit START $offset`,
owner-filtered point `CREATE/DELETE`, deterministic bound edge records in
`RELATE $sentence->$edge->$passage CONTENT $fields`, and
`used_in` filtering by both `owner = $user` and
`(in.owner = NONE OR in.owner = $user)` work with SDK transactions.
Two identical sentences can share a sentence row while using separate `part_of` edges with
distinct order values. Concurrent identical ingestion serializes through deterministic
passage/edge records with the existing `_atomic` conflict retry.
Injected failure after the first `used_in` write rolls back content, associations and dictionary
materialization. ENFORCED does not check owners: tests explicitly insert mismatched-owner edges
and show why repositories also recheck both endpoints. No migration/snapshot change is needed.
Observed edge-deletion caveat: deleting an endpoint automatically cascades **all** graph edges,
including foreign-owned edges. Content DELETE therefore checks foreign associations and returns
409 before mutation when any exist; replacements use UPDATE rather than DELETE/recreate.
The regression test proves foreign edge counts remain unchanged.

### Private image request/cache contracts (5.1.1) ✅

Verified 2026-11-14 against the existing **8101** SurrealDB test server with isolated
random migrated databases. Migration **0019** adds retry/cache/rate tables without changing
0007. Bound `CREATE` + media insertion + owner-filtered request update in SDK transactions
produces exactly one attachment under concurrent retries. Conflict retries remove losing files.
Owner-filtered `DELETE ... RETURN BEFORE` and request tombstoning remove only private rows;
path-reference lookup prevents removing a still-referenced file. Owner-scoped rate-row
`UPSERT ... revision += 1` serializes bounded queue submissions; provider rate windows store
only global counters. The generated snapshot reflects these new tables.
`UPSERT ... CONTENT` replaces omitted required fields on existing rows: `DEFAULT 0`
does not preserve an omitted `revision`. Rate refreshes explicitly include that field.

### Mnemonic context traversal (5.1.2) ✅

Verified with the existing isolated random-database harness on loopback **8101**:
bound `SELECT in FROM has_sense/has_lexeme WHERE out = $target AND
(owner = NONE OR owner = $user) ORDER BY id` supports canonical reverse ancestry reads.
Every returned endpoint is separately checked with `require_visible` in the same transaction;
edge visibility alone is not authorization. Changing/deleting target/ancestor content changes
the job content key. Existing `job`, `note.kind = mnemonic`, private `llm_cache` and atomic
per-owner daily budgets suffice; no migration or schema snapshot change is required.

### Morphology provenance and bounded group reads (4.3.2) ✅

Verified against existing loopback 8101, SurrealDB 3.3.5 / SDK 3.0, using migrated random
databases: migration 0021's optional source fields and composite owner/in/order index apply;
bound `out.* AS morpheme` expansion preserves composition order and source. Membership reads
authorize both dereferenced endpoints and edge owner, check `out.kind = 'morph_group'`,
then bind the authorized tag IDs to the candidate query. Repeated endpoint pairs with distinct
position-bearing relation IDs persist independently. Insert-only transaction retries preserve
private rows/edges and fail atomically on conflicting shared analyses. Retained probes:
`test_morphology.py`. No persistent development data or service state was changed.

### Sentence and passage schema contract (4.2.1) ✅

Verified 2026-11-14 against **SurrealDB 3.3.5 / SDK 3.0**, using fresh random databases on
the existing loopback **8101** server:

- The immutable `0005_dictionary.surql` already supplies SCHEMAFULL sentence/passage and
  ENFORCED `used_in` (sense → lemma/sentence/passage), `part_of` (sentence → passage).
  No new migration or snapshot change is required.
- Required context text/language/source/title/translation fields reject omission and NULL.
  Flexible sentence translation preserves multiple language keys, but each value must be a
  string. Undeclared top-level fields cause an error rather than being silently discarded.
- Optional `used_in.span` accepts NONE or exactly two integers, rejecting NULL, fractional and
  boolean elements. `part_of.order` is a required integer and rejects NULL/strings/booleans.
  Persisted order survives out-of-order insertion and direct replay of migration 0005.
- A no-op migration run and direct 0005 replay preserve populated context records, relation
  IDs, spans, ownership, order and the full schema. Normal snapshot comparison and synthetic
  drift detection pass without regenerating the committed snapshot.
- ENFORCED endpoints do **not** require matching owners: an Alice-owned `used_in` or `part_of`
  can point at Bob's existing private record. Edge-owner filtering alone does not authorize
  endpoint content; repositories/APIs must validate each endpoint and the edge independently.

Retained probes: `test_context_schema.py`, `test_dictionary_schema.py`,
`test_schema_snapshot.py`, `test_migrations.py`. No persistent dev database was changed.

### Bounded graph snapshots (4.4.1) ✅

Real migrated **8101**, SurrealDB 3.3.5: `FROM $targets` accepts bound record arrays,
including composite override record IDs. `in IN $authorized` / `out IN $authorized`
combine with owner dereferences, bound frontier arrays and bound `LIMIT $limit` for
bounded directional reads. Boolean negation uses `$induced = false`; `NOT $induced`
is not accepted by this parser. The SDK has no connection-level `merge`; use
`db.update(record).merge(fields)`. The real graph API and 10,201-edge dense fixture retain
these query/limit probes. No schema or persistent dev data was changed.
The same visibility, directional/induced relation and batched override/node query paths
also passed a read-only **8100** transaction probe with unique nonexistent IDs; it created
or changed no records and did not operate any service lifecycle.

### Hierarchical tags and relation deletion (4.3.1) ✅

Verified with SDK 3.0 against migrated random databases on existing loopback **8101**:
`SELECT *, out.* AS tag` expands the target record, and combined relation-owner and independently
dereferenced endpoint-owner predicates filter memberships. A real `user.tag_revision += 1`
write serializes concurrent opposing parent edits; the existing `_atomic` conflict retry
rechecks paths and yields one successful assignment plus one cycle conflict. Duplicate assignment
retries commit one owner edge. Incoming/outgoing cleanup and tag deletion roll back together.
**Deleting a relation endpoint automatically removes even foreign-owned incident relation edges.**
The API therefore rejects tag deletion when any shared/foreign incident edge exists, before
cleanup, rather than relying on an owner-filtered explicit edge DELETE to protect those edges.
The real API suite retains this corruption probe and the rollback/concurrency cases.
The bound relation expansion, independent owner filters and automatic endpoint cascade were
also verified on the existing **8100** development database using uniquely named scratch
tag/edge records; all scratch records were removed without changing schema or services.

### Recognition relation reads (3.2.3) ✅

Verified against the migrated isolated harness on existing loopback **8101**: owner-filtered
`relates_to`/`derives_to` reads accept bound selected sense/lexeme IDs, both endpoint-owner
dereferences and `(in = $selected OR out = $selected)`. Existing `has_sense`/`has_lexeme`
ancestry reads resolve either sense or lexeme targets with bound IDs and deterministic
`ORDER BY id LIMIT $limit`. Per-owner `_record` reads apply only that learner's overrides.
Recognition graph/API tests exercise incoming/outgoing semantic and derivation edges, private
endpoints/edges/ancestry and effective meanings without changing migrations or the dev database.

### Bounded distractor graph reads (3.2.2) ✅

Verified with SDK 3.0 against migrated isolated databases at `127.0.0.1:8101`:
bound `SELECT * FROM $targets` accepts arrays of record IDs; empty arrays return no records.
Relation-table filters can combine edge `owner`, dereferenced `in.owner`/`out.owner`,
`out.kind IN $kinds`, `out.pos`, and lemma `in.freq_zipf` numeric bounds.
Selecting `id` alongside endpoints permits stable `ORDER BY id LIMIT $limit`.
Both incoming and outgoing semantic edges are found with
`(in = $answer OR out = $answer)`. Owner-scoped deterministic override IDs are bulk-read
in the same transaction. The distractor integration tests verify private endpoint, tag,
ancestry/semantic edge and override isolation, plus oversized-synonym fail-closed behavior.
No dev database or migration is changed.

Check here before writing SurrealQL. **Status:** ✅ verified on the version shown · ❌ original
form is wrong (a working, verified replacement is given). New, unverified beliefs must be
tested before being used.

### Persisted study order and planning snapshots (3.1.3) ✅

Verified 2026-11-14 against SurrealDB 3.3.5 / SDK 3.0, isolated migrated databases on
existing `127.0.0.1:8101`: optional nonnegative `includes.study_order` survives visibility
updates without replacing IDs or timestamps. Bound owner/project/target updates assign all
legacy duplicate memberships the same position. Owner-filtered memory reads with bound
`sense IN $senses` handle empty arrays; owner history `at <= $end` includes completions exactly
at the read instant. Actual API tests verify persisted hidden slots, shared cards, every
content/edge ownership layer, UTC counts, schedules and forecasts. Existing membership/graph
lookup indexes and transaction helpers are reused. No persistent dev DB was modified.

### Durable exercise attempts (3.2.1) ✅

Verified 2026-11-14 against the existing SurrealDB 3.3 test server on **127.0.0.1:8101**,
using random harness databases, migration 0017 and real API/integration/snapshot tests:

- SCHEMAFULL enum status and `expires_at TYPE datetime ASSERT $value > $this.issued_at`
  migrate successfully. Required typed owner/project/sense references and the owner/expiry
  index are included in the regenerated table-level schema snapshot.
- Bound `CREATE $attempt CONTENT $content` and owner-filtered
  `UPDATE $attempt CONTENT $content WHERE owner = $user RETURN AFTER` preserve JSON-text
  Pydantic state (including UTC times, private keys, exact submissions and review receipts).
- Concurrent answer/hint mutations conflict on the same row; the existing SDK `_atomic`
  retry re-reads state, preserving one grade and the winning hint flag. Concurrent identical
  confirmations still produce exactly one atomic SRS update/log.
- A simulated failure after SRS commit but before the attempt status write leaves a durable
  review-log receipt. Retrying confirmation repairs attempt state without another review,
  even after expiry/project deletion; a different final rating remains a conflict.

No persistent dev database was changed.

### Atomic scheduling and preferences (3.1.2) ✅

Verified 2026-11-14 against SurrealDB 3.3.5 / SDK 3.0.0, isolated random harness databases
on existing loopback 8101:

- Flexible receipts use `DEFINE FIELD ... TYPE option<object> FLEXIBLE`, not
  `... FLEXIBLE TYPE ...` (the latter parser error was observed and corrected).
- Nested `prefs.desired_retention` defaults/backfills preserve existing preference fields.
  A bound nested `UPDATE` changes only retention. Optional fingerprint/receipt fields allow
  old logs to retain their schema-compatible data.
- **A no-op project UPDATE does not serialize review capacity.** The concurrent different-card
  limit test initially allowed both commits. A real `srs_revision += 1` write causes the
  existing transaction-conflict retry to rerun owner/tree/count checks; only one introduction
  commits when capacity is one.
- Bound owner/exercise/correct history reads ordered by `at DESC, id DESC LIMIT 100` retain
  the intended prior sample window. UTC `[start, next_day)` count filters distinguish
  introductions from later reviews in the project where each occurred.
- SDK transactions atomically persist complete cards, flexible JSON receipts and completed
  logs. Tests force failure after both writes and observe rollback; same-attempt concurrent
  retries yield one update/log, distinct stale attempts reject and conflicting retry data fails.

Retained probes: `test_srs_reviews.py`, `test_srs_limits.py`, `test_srs_preferences.py`,
`test_srs_memberships.py` and the schema snapshot tests.

### Memory and completed review history (3.1.1) ✅

Verified **2026-11-14**, SurrealDB **3.3.5** / SDK **3.0.0**, against fresh isolated
databases on the existing **8101** server (no dev database changes):

- Migration `0013` uses normal SCHEMAFULL tables for `memory` and `review_log`.
  `DEFINE FIELD ... id ON memory ASSERT $value =
  type::record('memory', [$this.owner, $this.sense])` enforces the nested array ID.
  Required owner/sense fields can independently assert against `record::id($this.id)[0/1]`.
  Valid IDs containing two bound RecordIDs round-trip; arbitrary IDs, mismatched owners
  and mismatched senses fail. Replay with `IF NOT EXISTS` preserves schema and records.
- `option<int>`, `option<float>` and `option<datetime>` retain absent FSRS values as NONE,
  not NULL; NULL is rejected. UTC datetime microseconds and fractional floats survive.
  State/rating range assertions and 0..60,000 ms duration assertions reject invalid writes.
- `(owner, sense)` UNIQUE plus the canonical memory ID establish one card per owner/sense;
  `(owner, due)` and `(owner, at)` index owner-scoped queue/history access.
  `(owner, attempt_id)` UNIQUE rejects a second completed log even in a different project,
  while another owner can use that attempt string without sharing the receipt.
- `record<project>` on a normal log table does not cascade or require project existence.
  The production project-delete transaction removes memberships and projects, preserving
  both users' cards and logs, including the original project references. Log owner asserts
  against its memory ID's owner component, without depending on project existence.

Retained probes: `tests/integration/test_memory_schema.py`, `test_schema_snapshot.py`.
The card field contract was checked against upstream
[py-fsrs v6.3.0 Card](https://github.com/open-spaced-repetition/py-fsrs/blob/v6.3.0/fsrs/card.py):
`card_id`, `state`, `step`, `stability`, `difficulty`, `due`, `last_review`.
The dependency/wrapper are task 3.1.2; no package installation or runtime scheduler behavior
is claimed by these schema tests.

### Optional LLM cache and budget (3.2.5) ✅

Verified 2026-11-14 against isolated migrated databases on existing **8101**, SurrealDB
**3.3.5** / SDK **3.0.0** (no dev database or stack lifecycle operations):
`0014`'s unique `(owner,key)` cache index accepts shared `owner=NONE` and distinct owner rows.
Deterministic `llm_budget:[user,UTC-day]` records and owner/day-filtered SELECT followed by
conditional `UPDATE ... SET attempts += 1 ... AND attempts < $limit RETURN AFTER` inside
the existing conflict-retried UUID transaction reserve attempts atomically, including first
CREATE races. Concurrent reservation and concurrent mock-provider dispatch tests both enforce
the cap. UTC offset conversion/reset and independent owners are retained regressions.
Cache reads explicitly match the exact owner (NONE only for shared generation); shared source
reads use `owner = NONE` and only approved dictionary fields enter prompts.
The full backend snapshot-update suite passed 581 tests; the final normal backend suite passed
584 tests with the snapshot unchanged. Repository `check` passed. Tests use SDK MockTransport only.

### Project tree visibility (2.3.4) ✅

Verified **2026-11-14**, SurrealDB **3.3.5** / SDK **3.0.0**, using only random migrated
harness databases on the existing **8101** test server:

- `DEFINE TABLE OVERWRITE includes TYPE RELATION IN project OUT lemma | lexeme | sense |
  sentence | passage ENFORCED SCHEMAFULL` extends the endpoint union and updates the implicit
  `out` field type without losing fields, indexes or existing memberships. Migration `0012`
  is forward-only; `0006` remains unchanged. Existing replay/schema tests verify the updated
  contract and valid lexeme membership, while wrong/nonexistent endpoints remain rejected.
  New `(in, owner, out)` indexes on `has_lexeme` and `has_sense` support the tree's
  bound parent/owner/selected-target lookups; `includes` reuses its existing lookup index.
- Bound `type::table($table)` relation reads can combine owner filters on relation and both
  endpoints with `($targets = NONE OR out IN $targets)` and bound `LIMIT`. An empty target
  array selects no edges, so an empty sense selection cannot expose cached meanings.
- Owner/project/target-filtered `UPDATE includes SET hidden = $hidden ... RETURN AFTER`
  preserves edge IDs/timestamps. Lazy lexeme `RELATE` markers commit in the same SDK
  transaction as owner-safe ancestry validation; ancestor restoration does not alter sense flags.
- Dictionaries and requester overrides reuse the existing transaction-aware effective `_record`
  helper. Tests exercise private endpoints, foreign dictionary relations and foreign includes
  edges attached to otherwise shared/own rows; all are independently excluded.

Retained probes: `tests/api/test_project_tree.py`, `tests/api/test_project_tree_visibility.py`,
`tests/integration/test_project_schema.py`.
The generated schema snapshot includes the extended `includes` table and endpoint type.

### User dictionary API (2.3.3) ✅

Verified on **2026-11-14** using SDK **3.0.0**, the existing loopback test server **8101**
and migrated, random harness databases (no dev database or server lifecycle changes):

- Bound `UPDATE $overlay SET fields = $fields, updated_at = $now WHERE owner = $user
  RETURN AFTER` replaces the entire flexible `fields` object, including replacement with `{}`.
  Recursive PATCH merging is performed in Python before that assignment. Thus PUT reliably
  drops omitted keys rather than relying on nested MERGE semantics.
- Deterministic owner/target overlay IDs work with separate owner-filtered SELECT/UPDATE/DELETE
  and CREATE in an SDK transaction. Reset never touches the target or another owner's overlay.
- Creating a user-owned sense and `RELATE $lexeme->$edge->$sense CONTENT $content` with a
  user-owned bound edge ID commits atomically. Effective entry reads expose it only to its
  creator and leave existing shared rows/edges unchanged.
- Owner/target-filtered note lists (`ORDER BY id`), owner-filtered note mutation and independent
  target visibility checks work inside the same SDK transaction. A deleted/foreign target
  cannot be accessed through a retained note/overlay row.

API regression coverage lives in `test_overrides.py`, `test_user_dictionary.py`, `test_notes.py`.
No migration or snapshot change is needed; these reuse `0005` and `0006`.

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

### Shared pronunciation attachment (2.5.2) ✅

Verified against isolated migrated databases on the existing test instance **8101**
(SurrealDB 3.3.5 / SDK 3.0.0 / Python 3.14.3): owner-filtered `has_lexeme` endpoint checks,
`media` lookup using the existing `media_target` index, and UUID transactions updating
`lexeme.pron` with bound arrays containing `RecordID("media", ...)`. The existing
`pron.*.audio` field preserves record references and effective reads encode opaque IDs.
An empty-string IPA permits an audio-only accent entry without fabricating a transcription.
Private media cannot be attached to shared pronunciations. No migration is necessary.
### Shared enrichment metadata (2.4.3) ✅

Verified against the existing isolated test databases on **8101**, SurrealDB **3.3.5** /
Python **3.14.3** / SDK **3.0.0**: migration `0010`'s optional arrays of typed objects
retain frequency/tag source attribution; absent nested option fields decode as omitted keys.
Bound `UPDATE $record MERGE $fields WHERE owner = NONE` updates only existing shared lemma
metadata within the same UUID transaction as insert-only deterministic dictionary edges.
Shared `derives_to` edges retain optional source attribution and `via`; both base-first and
derived-first fixture sequences yield exactly one base → derived edge. Shared semantic edges
retain exact source/type/direction; absent/private related endpoints do not get imported.
The registered worker claim/dispatch tests verify persisted metadata, overlays, retry/recovery
and context cleanup using the real SDK. No dev database or shared server lifecycle changes.
Verification: focused enrichment/dictionary/worker/reader suite **29 passed**; full
`dev.ps1 test -Backend -UpdateSnapshot` **488 passed**, one existing Starlette/httpx warning;
normal snapshot-comparison suite **10 passed**; `dev.ps1 check` clean. Initial required
check/test attempts lacked `ruff`/`pytest`; `uv sync --frozen` restored the locked environment.
The initial focused test's short password and a `Value`/iterable typing error were corrected.
Pylance's linked-worktree symbol lookup returned no symbols; basedpyright reported no errors.
The initial commit hook rejected root-vs-backend import classification of the fixture builder;
the optional-build test now imports it locally, and both check contexts are validated.

### Atomic add-to-project boundary (2.4.2) ✅

Verified on SurrealDB 3.3.5 / SDK 3.0.0 using isolated migrated databases on test port
8101 (no dev database changes): owner-filtered project validation, dictionary materialization,
bound `RELATE $project->$edge->$target CONTENT $content` with
`includes:[project, target]`, matching-owner `UPDATE includes SET hidden = false`, and
job inserts/owner-filtered dedup reads all share the same SDK `txn_id`.
Injecting an enqueue failure after a prior job insert rolls back dictionary records,
memberships and jobs together. Concurrent adds exercise the existing transaction-conflict
retry helper without duplicate memberships/jobs. Migration `0008`'s
`DEFINE INDEX IF NOT EXISTS includes_owner_project_target ON includes FIELDS owner, in, out`
is accepted and captured in the schema snapshot. Restoring selected hidden edges preserves
their original IDs and `added_at`; omitted hidden edges remain unchanged.

Task **2.2.3**, **2026-11-14**, verified dictionary materialization/effective reads against
the existing loopback **test** server (**8101**, **surrealdb-3.3.5 / Python 3.14.3 / SDK 3.0.0**),
using the migrated harness database, fixture lexicon and fresh users:

- ✅ Bound deterministic relation IDs (`RELATE $start->$edge->$end CONTENT $fields`) accept
  nested start/end RecordIDs plus position or relation-type/source identity components.
  Point reads followed by CREATE/RELATE inside a UUID SDK transaction are insert-only and
  idempotent. Concurrent first imports converge through the existing transaction-conflict
  retry helper; composition positions and reciprocal semantic edges remain distinct.
- ✅ `SELECT id FROM $record WHERE owner = NONE` plus
  `RETURN [{exists: record::exists($record)}]` distinguishes a missing shared identity from an
  occupied private identity **without reading private fields**. A private collision causes
  409 and rolls back earlier shared rows in that transaction.
- ✅ `SELECT ->(? WHERE (owner = NONE OR owner = $user)
  AND (in.owner = NONE OR in.owner = $user)
  AND (out.owner = NONE OR out.owner = $user)).* AS edges
  FROM $target WHERE owner = NONE OR owner = $user` returns direct outgoing relation records;
  `<-(? WHERE ...)` is the incoming counterpart. These are graph-adjacency lookups, not
  relation-table scans. Python bounds results to dictionary relation tables, deduplicates
  IDs across directions and separately checks endpoint existence/ownership. Shared or
  matching-owner edges cannot expose a foreign endpoint, nor can a foreign edge between
  shared endpoints become visible. Existing graph storage suffices; no new indexes or
  migrations were introduced.
- ✅ Point reads of `override:[user, target]` with `WHERE owner = $user` reject a mismatched
  owner even when the nested ID names the requester. Effective nested-map merging is
  read-only Python projection in the same SDK transaction; shared rows, both users' overrides
  and custom content remain unchanged across repeat imports and reads.

The focused suite `tests/integration/test_dictionary.py` passes **4 tests**, including
selection preflight, incremental sense enrichment, concurrent/repeated imports, retained
custom content/overlays, source affixes/relations and both-direction cross-user isolation.
Initial required check/test attempts reported missing `ruff`/`pytest`; `uv sync --frozen`
restored the locked backend environment. The full backend run passed **456 tests** with the
existing Starlette/httpx deprecation warning; `dev.ps1 check` passed. No dev database access,
server lifecycle changes, schema changes or API regeneration were needed.

Task **2.3.2**, **2026-11-14**, verified project repository queries against the existing
loopback **test** server (**8101**, **surrealdb-3.3.5 / Python 3.14.3 / SDK 3.0.0**)
using the migrated harness database and unique users/records:

- ✅ Owner-bound `SELECT * FROM project ... ORDER BY created_at DESC, id LIMIT $limit
  START $start` and `SELECT count() ... WHERE owner = $user GROUP ALL` return isolated
  pages/counts in one SDK transaction.
- ✅ `CREATE $project CONTENT $content RETURN AFTER` accepts nested plans with optional
  Python None fields (database NONE); `UPDATE $project MERGE $changes WHERE owner = $user
  RETURN AFTER` replaces a supplied plan object and preserves omitted top-level fields.
  Wrong-owner and absent-target updates return no rows, not new projects.
- ✅ Inside a UUID SDK transaction, `DELETE includes WHERE in = $project AND owner = $user`
  then `DELETE $project WHERE owner = $user RETURN BEFORE` removes only the target project and
  its memberships. Shared/custom target records and reusable notes/overrides survive.
  The preflight `SELECT id FROM includes WHERE in = $project AND in.owner = $user
  AND owner != $user LIMIT 1` detects inconsistent cross-owner membership before endpoint
  deletion can cascade it; the API rejects this state with 409 and no changes.

The focused project API/cleanup suite passed **8 tests**, including validation, authentication,
not-found, cross-user access, pagination and retained unrelated records. No schema migration,
dev database access or shared server lifecycle change was needed.
Final `dev.ps1 check`, `gen-api`, `test -Backend` (**351 passed**, no skips) and
`test -Frontend` passed; the backend retains the existing Starlette/httpx deprecation warning.
Initial check/test attempts failed because this new worktree lacked `ruff`/`pytest`;
`uv sync --frozen` restored the locked backend environment. The existing generation command
restored its missing local pnpm dependencies. Pylance's file check could not resolve the linked
worktree file; Ruff and basedpyright successfully validated the Python sources instead.

Task **2.3.1**, **2026-11-14**, verified `0006_project_overlays.surql` on the existing
loopback **test** server (**8101**, **surrealdb-3.3.5 / Python 3.14.3 / SDK 3.0.0**).
`tests/integration/test_project_schema.py` uses fresh harness databases, checks INFO field/index
definitions and endpoint unions, and replays both the migration runner and raw DDL with an
identical full snapshot and retained project data. No dev database or shared server lifecycle
changes are involved.

- ✅ `TYPE RELATION IN project OUT lemma | sense | sentence | passage ENFORCED SCHEMAFULL`
  accepts each documented endpoint, rejecting lexemes, wrong source tables and missing endpoints.
  An owner-bound UPDATE toggles `hidden` on the same edge without changing `added_at` or the
  dictionary record. Visibility probes filter project, edge and target ownership independently.
- ✅ Required `record<user>` owners reject NONE, NULL, strings and wrong-table references.
  Project plan nested integer fields and optional datetime/integer fields retain valid values;
  malformed values and missing `daily_new` fail. No numeric range or business defaults are
  implied by these types.
- ✅ Override `fields TYPE object FLEXIBLE` preserves nested language maps and arrays.
  Bound `RecordID("override", [user, target])` UPSERT repeatedly updates the same row;
  another user/target has a different identity. Owner-bound DELETE resets only that overlay,
  leaving the shared target and another user's edits unchanged. The deterministic ID shape and
  ID-owner agreement remain repository contracts rather than database assertions.
- ✅ Note `target TYPE record` accepts a reference to any table without requiring its existence;
  literal `note | mnemonic` kind types and `note(owner, target)` indexing work as declared.
  Alice/Bob owner-filtered note and overlay reads remain disjoint. Typed references are not
  authorization: future APIs must validate target visibility and ownership.

Verification: the focused project schema suite passed **22 tests**; `dev.ps1 check` passed;
`dev.ps1 test -Backend -UpdateSnapshot` and the subsequent normal `test -Backend` each passed
**343 tests**, with no skips. Both full runs reported the existing Starlette/httpx deprecation
warning. Initial check/test attempts failed because the new worktree lacked `ruff`/`pytest`;
`uv sync --frozen` restored the locked backend dependencies before successful reruns.
Project CRUD, tree/override/note APIs and media are outside this migration task.

Task **2.2.1**, **2026-11-14**, verified `0005_dictionary.surql` using the existing loopback
**test** server on **8101**, HTTP version **surrealdb-3.3.5**, Python **3.14.3**, SDK **3.0.0**.
`tests/integration/test_dictionary_schema.py` uses fresh harness databases, checks all documented
field types and relation endpoint sets through `INFO`, exercises accepted/rejected writes and
shared/Alice/Bob owner-filtered reads on every table/edge, and replays both the migration runner
and raw DDL without schema changes or data loss. It never uses the dev database or changes the
shared server lifecycle.

- ✅ Nested SCHEMAFULL object arrays: `TYPE array<object>` plus `forms.*.form`,
  `forms.*.tags TYPE array<string>`, `pron.*.accent` and `pron.*.audio` retain and validate nested
  values. A missing required form, invalid accent, non-string tag or wrong audio record table fails.
- ✅ Dynamic language maps: `DEFINE FIELD ... gloss ON sense TYPE object FLEXIBLE;` followed by
  `DEFINE FIELD ... gloss.* ON sense TYPE string;` preserves `zh` and `fr` keys while rejecting
  numeric translations. `translation` uses the same pattern. **`FLEXIBLE TYPE object` is rejected**:
  the server explicitly requires FLEXIBLE after TYPE.
- ✅ `TYPE option<array<int, 2>>` permits an absent span or exactly two integers, rejecting
  one/three elements and a string element. `INFO` normalizes option types to `none | ...`.
- ✅ Relation unions use `IN sense | morpheme | tag OUT tag ENFORCED SCHEMAFULL` and
  `IN sense OUT lemma | sentence | passage ENFORCED SCHEMAFULL`. Each allowed endpoint combination
  succeeds; wrong endpoint tables and nonexistent records fail.
- ✅ Dynamic `RELATE $start->$edge->$end CONTENT $attributes` works when `$edge` is a bound
  **RecordID** in the relation table. Binding its table name as a plain string fails (interpreted
  as an invalid `out` value); the test helper binds generated RecordIDs instead.
- ✅ Every dictionary owner is `option<record<user>>`: NONE/shared and user references round-trip;
  NULL, strings and wrong reference tables are rejected. References constrain table type, not
  user/media record existence. Cross-owner edge pairs are allowed; no speculative unique edge
  index blocks user overlays. `lemma(lang, text)` remains globally unique as documented.

Task **1.5.4**, **2026-11-14**, verified against the existing loopback **test** server
(8101), **surrealdb-3.3.5**, SDK **3.0.0**. Migration `0004_admin_guard.surql` adds
an internal SCHEMAFULL singleton with an integer `version`; `UPDATE admin_guard:singleton
SET version += 1` is a real shared write inside UUID transactions. Synchronized two-admin
cross-disables and cross-demotions both start from exactly two enabled admins plus one
disabled admin. One commits, the other encounters a transaction conflict and retries its
authorization check, returning forbidden; exactly one enabled admin remains. Tests assert
at least three authorization attempts across the two operations. Bound `LIMIT $limit
START $start`, `ORDER BY username, id`, `SELECT count() AS total ... GROUP ALL`, and
explicit `CREATE/UPDATE ... RETURN` public-field projections work as used in `db/admin.py`.
Password/role/disabled mutations and owner-bound refresh revocation commit together;
temporary plaintext passwords are never sent to DB. Fresh harness databases are removed
individually; no dev DB or shared server lifecycle changes.

Migration numbering intentionally leaves `0003` for the independent job task. The migration
loader determines pending files by applied-version membership, not by a highest-version
watermark (`run_migrations`), so a subsequently added `0003_job.surql` can be applied after
`0004`; fresh combined migrations run in numeric order. Parent must regenerate the combined
schema snapshot after merging both branches.

Task **1.5.1**, **2026-11-14**, reverified auth DDL on the loopback **test** server (8101),
reporting **surrealdb-3.3.5**, with SDK **3.0.0**. `0002_auth.surql` and
`tests/integration/test_auth_schema.py` verify literal string unions (`'admin' | 'user'`,
theme and accent), SCHEMAFULL nested object fields, required booleans, typed `record<user>`
and `option<record<refresh_token>>`, optional datetimes, and unique username/hash indexes.
Duplicate writes fail naming their unique index; wrong role/theme/accent/reference table and
string expiry/boolean values are rejected. UTC expiry/revocation datetimes and replacement
record IDs round-trip. All writes use fresh harness databases, removed individually on teardown;
the dev database is untouched. The snapshot runner captures the accepted field/index definitions.

Task **1.5.2**, **2026-11-14**, verified auth repositories on the same isolated **8101**
server/SDK (**3.3.5 / 3.0.0**). `tests/integration/test_auth.py` exercises bound record targets,
`UPDATE ... WHERE user = $user AND id IN $family`, atomic multi-statement CREATE/UPDATE,
and explicit SDK transactions. `$token` is a **protected variable** in 3.3.5 and binding it
fails; use `$refresh_id` instead. Forced simultaneous reads on independent WebSocket
connections produce a structured server error with
`details.kind == QueryDetailKind.TRANSACTION_CONFLICT` (`"TransactionConflict"`); cancel,
start a new transaction and reread the credential. A conflict can already terminate the server
transaction, so a failed cancellation must be safely logged, not prevent that structured retry.
The regression requires a retry and proves
that exactly one rotation wins, the replay fails generically, and its committed revocation
includes the winning replacement. Whole-family tests also prove reverse-link ancestry,
independent-login and cross-user isolation. Bootstrap's stable `user:bootstrap_admin` CREATE
inside a transaction, followed by conflict retry/recheck, creates one admin on concurrent
starts without updating an existing password. No migration or snapshot change was needed.

Task **1.5.3**, **2026-11-14**, verified password/session mutations on the same isolated
**8101** instance (**3.3.5 / SDK 3.0.0**), through `tests/api/test_auth_password.py` and
`test_auth_endpoints.py`. Within the existing conflict-retrying SDK transaction, an
`UPDATE $user ... WHERE id = $user AND disabled = false AND password_hash = $expected_hash`
returns the updated user only when the verified hash is still current. The transaction then
revokes `refresh_token` rows with `WHERE user = $user` and creates the replacement session.
Wrong-password and rejected-update paths leave user/session state unchanged; successful
password change revokes independent old logins without affecting another user's sessions.
Logout binds the authenticated subject before revoking the cookie's family. Forced-change
refresh returns the user without rotating, allowing the service to raise its domain 403.
The assembled backend suite passed **158 tests**, with no skips; no schema change was needed.

All snippets below target **server 3.3.5 / Python SDK 3.0.0**. Executable versions live in
`app.db.spike_support`, `spike_records`, `spike_graph`, and `spike_operations`; do not move
SurrealQL into scripts, API handlers, or services.

### Job worker verification (task 1.6.2, 2026-11-14)

Verified ✅ on **surrealdb-3.3.5 / SDK 3.0.0**, against individually generated migrated
databases on the loopback test server **8101**, never the dev/production database:

- `DEFINE FIELD ... TYPE object FLEXIBLE` retains arbitrary nested job payloads in
  SCHEMAFULL tables. The initially attempted `FLEXIBLE TYPE object` was rejected by the
  server parser: FLEXIBLE must follow TYPE. `0003_job.surql` uses the accepted form.
- `SELECT ... WHERE status = 'queued' AND run_after <= time::now() ORDER BY run_after
  LIMIT 1` selects candidates. `UPDATE $id SET status = 'running', attempts += 1,
  error = NONE WHERE status = 'queued' AND attempts = $attempts AND run_after <=
  time::now() RETURN AFTER` is the atomic claim. Synchronized reads on **two independent
  WebSocket connections** select the same row; only one conditional UPDATE returns it,
  exactly one handler runs, and the stored job is done with attempts = 1. Structured
  `TransactionConflict` is retried with bounded delay; all other errors propagate.
- Bound UTC `run_after` values round-trip and exclude retries from immediate polling.
  Retry tests verify the actual scheduled times, 1/2/4/8 seconds between attempts,
  permanent failure at attempt five, and immediate terminal failure for unknown handlers.
  Completion/retry UPDATEs also compare the claim's attempts, running status and owner.
- `LIVE SELECT * FROM job WHERE status = 'queued'` returns a query UUID;
  `await subscribe_live(id)` returns an async generator. Enqueue produces CREATE, and
  changing running back to queued produces UPDATE. KILL plus `aclose()` ends the stream.
  SDK 3.0.0 documents and the disconnect test observes subscription failure after loss
  of its own socket. The worker uses a separate connection with reconnect disabled,
  logs failure without messages/payloads, closes it and establishes a **new** subscription
  after five seconds. A fresh enqueue then wakes it again. Independent polling continues
  when LIVE setup fails; cancellation tests confirm no remaining worker/SDK tasks.
- `GET /api/jobs/{id}` binds `RecordID("job", key)` and `owner = $user`; absent,
  malformed, other-owner and shared jobs all return the same 404. Only generated lowercase
  32-hex keys are accepted; query fragments are never parsed as record identifiers.

The migration loader checks each discovered version against the set already applied,
not a highest-version watermark; an unapplied `0003` can therefore follow an already
applied `0004` when both immutable files are present. Fresh databases apply them sorted.
The combined post-merge snapshot must contain both job and admin-guard definitions.

Verification: baseline backend **158 passed**; the full normal (snapshot comparison)
suite after jobs/LIVE integration **170 passed**, with only the existing Starlette
TestClient deprecation warning. Explicit `--update-snapshot` succeeded first. After
adding the Windows signal-restoration regression, the final focused worker/API/snapshot
selection passed **15 tests**. Ruff check/format and basedpyright are clean; generated
OpenAPI/TypeScript contracts pass scoped ESLint and frontend typecheck. Production
image/Compose/browser acceptance is deferred to the integrated parent run.

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

### Media metadata (task 2.5.1) ✅

Migration `0007_media.surql` and real API tests on isolated databases at test port 8101
verify `record<lemma | lexeme | sense | morpheme | tag | sentence | passage>`,
optional enum `option<'US' | 'UK'>`, typed optional user ownership and target indexing.
Bound `CREATE $id CONTENT $data` persists SDK record references; bound
`SELECT * FROM $id WHERE owner = NONE OR owner = $user` isolates media owners.
An independent bound `SELECT id FROM $target WHERE owner = NONE OR owner = $user`
checks current target existence/visibility. With `$user = NONE`, only shared targets
match, so trusted shared writes cannot attach to a private target. Verified through
the migrated backend suite (snapshot-update mode); no shared dev database was changed.
