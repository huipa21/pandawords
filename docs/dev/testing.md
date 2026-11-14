# Testing

## Scheduling service (3.1.2)

Focused command from `backend`, using isolated random databases on the healthy existing
`127.0.0.1:8101` server:

```powershell
uv run --no-sync pytest -q tests\unit\test_srs.py tests\integration\test_srs_memberships.py tests\integration\test_srs_reviews.py tests\integration\test_srs_limits.py tests\integration\test_srs_migration.py tests\integration\test_project_add_atomic.py tests\api\test_srs_preferences.py
```

Tests execute py-fsrs 6.x, checking complete card round-trips, first/repeat/second-project adds,
hidden legacy reconciliation, cross-owner cards and preferences, add/review rollback,
manual ratings and retention-dependent scheduling. Real concurrent confirmations cover
identical retries, conflicting final ratings, stale attempts and per-project capacity across
different cards. Persisted receipts survive subsequent scheduling updates. Eligibility is
revalidated after ancestor/sense hiding or project deletion; failures leave cards/logs intact.
Timing tests cover wrong/give-up/hint, both kinds, exact fast/slow boundaries, 19/20 samples,
last-100 history, type/user/correctness isolation and the integer 60-second cap. UTC boundary
tests distinguish first introduction counts from later same-day/other-project review counts.
New preferences API tests reject invalid retention and owner injection without overwriting
other settings. `dev.ps1 test -Backend -UpdateSnapshot` regenerates migration `0015`'s schema;
the normal backend runner checks it without rewriting.

Verification on 2026-11-14: `dev.ps1 check`, frontend tests and API generation passed.
The final normal backend suite passed 632 tests; the focused suite including auth/schema-drift
regressions passed 55 tests. The snapshot-update run generated the schema but initially failed
one old auth-schema assertion that omitted the new default; that assertion was updated to
verify preserved old fields plus retention. API generation also exposed two typed frontend
auth/admin fixtures missing retention; their fixture values were updated and linted.
The legacy migration test initially tried the new service model against the old SCHEMAFULL
schema; it now inserts the authoritative old shape before testing the forward backfill.
Pylance could not resolve the worktree's new file; ruff, basedpyright and actual runtime tests
provide validation. The existing Starlette/httpx deprecation warning remains. No E2E,
dev-database mutation or stack lifecycle operations were performed.

## Memory and completed review schema (3.1.1)

From `backend`, with the existing loopback SurrealDB 3.3 server on **8101**, run:

```powershell
uv run --no-sync pytest -q tests\integration\test_memory_schema.py tests\integration\test_schema_snapshot.py tests\integration\test_migrations.py tests\integration\test_project_schema.py
```

The memory tests use `fresh_db` and migrate each isolated database, removing only their own
database on teardown. Actual `INFO FOR TABLE` field types and all four access/unique indexes
are checked. Writes exercise all seven upstream py-fsrs 6.3.0 serialized card fields for
Learning, Review and Relearning, including optional values and UTC microseconds; they do not
yet execute the FSRS scheduler (task 3.1.2). Invalid types, missing/foreign owners,
noncanonical card IDs, duplicate cards, duplicate completed attempts across projects,
rating/state/duration boundaries, two owners and owner-filtered history are covered.
Two project memberships share one card; hide/restore and the production project-delete
transaction preserve cards/history. Another owner's delete fails without removing the project.
Migration replay preserves data/schema; the standard fresh snapshot tests check drift and
the diagnostic for a new migration. Update explicitly with the snapshot flag/runner described
below, then run without it to verify the committed artifact.

Pylance's file-syntax tool could not resolve the worktree's new test file; ruff, basedpyright
and real runtime tests provide validation instead. The initial schema test used an invalid
dictionary register scalar, then an unencoded user subject in the deletion probe; both fixture
errors were corrected to the existing array and opaque-subject contracts.

Verification on 2026-11-14: repository `dev.ps1 check` passed; the focused schema/migration
suite passed **65 tests**, explicit snapshot generation passed, and the subsequent normal
`dev.ps1 test -Backend` passed **587 tests** with the existing Starlette/httpx deprecation
warning. The first check found missing ruff; manifest-based `uv sync` and `pnpm install`
restored this worktree's tools without dependency changes. No E2E, stack lifecycle operation,
dev-database mutation or bulk cleanup was performed.

## Optional DeepSeek client (3.2.5)

From `backend`: `uv run --no-sync pytest -q tests\integration\test_llm.py`.
The real OpenAI SDK uses `httpx.MockTransport`; no test contacts DeepSeek. Isolated migrated
8101 databases cover strict valid/invalid JSON, caller rejection on fresh/cached results,
canonical cache reuse, prompt/schema/model/input versioning, disabled keys, HTTP/network
failures, timeouts, retry accounting, zero/exhausted budgets, concurrent reservations, UTC
reset with offset-aware times, owner isolation, shared source provenance and debug log hygiene.
Migration `0014` must be included when regenerating/comparing the schema snapshot.
Run `dev.ps1 test -Backend -UpdateSnapshot`, then normal backend tests and `dev.ps1 check`.
Exercise-level fallback is intentionally owned by tasks 3.2.6 and 3.3.2.

Verification on 2026-11-14: full backend snapshot regeneration passed **581 tests**,
then normal migration/LLM regression comparison passed **35 tests**; `dev.ps1 check` passed.
After adding actual-schema invalidation, zero-budget cache reuse and non-standard JSON-number
regressions, the final normal full backend suite passed **584 tests** (28 LLM cases), and
`dev.ps1 check` passed again. Pylance syntax validation, basedpyright and Ruff passed.
An initial overly short mock timeout hit the SDK's cold startup and was increased for normal
mock calls while keeping a dedicated short timeout case. Initial missing tooling was restored
with `uv sync`; the dependency lock only adds OpenAI and its required transitive packages.
The existing Starlette/httpx deprecation warning remains. No live provider, E2E or dev-stack
commands were run.

## Project tree API (2.3.4)

From `backend`, run `uv run --no-sync pytest -q tests\api\test_project_tree.py
tests\api\test_project_tree_visibility.py
tests\integration\test_project_schema.py`. The isolated migrated harness on existing port
8101 covers empty/selected-only trees, requester overlays, stable IDs/content, hidden
senses/ancestors, independent lexeme markers, restored membership history, pagination and
explicit bounds, strict visibility inputs, authentication and project/row/relation/membership
owner isolation. Schema tests now accept lexeme endpoints introduced by forward migration
`0012`; `0006` is immutable. Regenerate with `dev.ps1 test -Backend -UpdateSnapshot`,
then run normal backend tests to verify the committed snapshot without rewriting it.
Use `include_hidden=true` for UI/E2E restore controls and PATCH the node's own `hidden` flag;
do not infer direct sense hiding from `effective_hidden` inherited from an ancestor.
Tree API tests override `test_settings`/`db` with the existing `job_settings`/`job_db`
fixtures, giving each test its own migrated database. This prevents broad cached fixture
materialization from changing later dictionary repository tests' initial selections.

Verification on 2026-11-14: snapshot-update and normal backend suites passed **525 tests**;
repository `check` and frontend tests passed. Initial `check` found missing `ruff`, resolved
by `uv sync`. The first backend run exposed two dictionary tests contaminated by the tree
tests' shared source cache; per-test database isolation fixed both. A frontend token-enforcement
test initially hit its 20-second timeout under concurrent checks; the unchanged suite passed
on rerun. Backend emits the existing Starlette/httpx deprecation warning. Pylance editor tools
could not resolve this worktree's new Python file; `basedpyright`, ruff and runtime tests
provide the validation instead. No E2E or persistent dev-database operations were performed.

## Layers

| Layer | Tool | Location | Covers |
|---|---|---|---|
| Unit (backend) | pytest | `backend/tests/unit` | Pure logic: auto-rating, plan pacing, lexicon parsing, ID encoding, distractor ranking |
| Integration | pytest + real SurrealDB 3.3 (port 8101) | `backend/tests/integration` | Repositories, migrations, owner isolation, graph queries |
| API | pytest + httpx `ASGITransport` | `backend/tests/api` | Endpoints, auth, error codes, cross-user access returns 404 |
| Unit (frontend) | vitest + @vue/test-utils | `frontend/src/**/*.test.ts` | Composables, stores, components with logic (RatingBar keys, SenseSelectList pre-check) |
| E2E | Playwright | `frontend/e2e` | Critical flows only, against the `dev.ps1 up` stack on `main` |

## Commands

`./scripts/dev.ps1 test` runs everything except E2E. `-Backend`, `-Frontend` and `-E2E` select one
layer, and selectors can combine (duplicates run only once). E2E is explicit only: it requires
the main worktree, a ready stack on 5173, and `frontend/playwright.config.ts`; a
missing config or tool fails rather than silently skipping tests. The hook runs
`pnpm exec playwright test`, using that config. `-UpdateSnapshot` requires the backend selector.
The output is quiet (`pytest -q`, vitest `dot` reporter). On failure it prints the full
failure output.

### First-login E2E

From `main`, run `.\scripts\dev.ps1 up`, then `.\scripts\dev.ps1 test -E2E`.
The runner imports the main worktree's `.env.dev`; both `ADMIN_USERNAME` and
`ADMIN_PASSWORD` must identify an enabled administrator whose initial password change
is already complete. Missing credentials fail the test without printing their values.
The existing API, worker, database, and Vite stack must remain running. Playwright uses
`http://localhost:5173` and never starts another stack.

Install the matching Chromium binary once from `frontend` with
`pnpm exec playwright install chromium` if Playwright reports that it is missing.
`pnpm test:e2e` runs the same test directly with the credentials already exported.

### Project-to-word E2E

`frontend/e2e/project-word.spec.ts` creates a uniquely named project, adds the fixture word
`run`, overrides its first sense definition, hides that sense in the project tree, and checks
through the API that the effective entry still contains the sense and override. It deletes its
project in `finally`. Start the stack offline and fixture-backed before running it:

```powershell
$env:LEXICON_PATH = "$PWD\backend\tests\fixtures\lexicon_small.sqlite"
$env:AUDIO_NETWORK_ENABLED = 'false'
.\scripts\dev.ps1 up
.\scripts\dev.ps1 test -E2E
```
`pnpm exec playwright test --list` checks discovery without credentials or a running stack.
Only Chromium runs, with one worker, no retries, and no skipped/fallback cases.
Vitest's `src/**/*.test.ts` include keeps `e2e/**/*.spec.ts` out of unit runs.

The single flow selects English via the existing browser preference format, signs in as
the administrator, creates a unique `e2e_<UUID>` learner, reads the temporary-password
dialog, signs out, and signs in as that learner. It verifies the public forced-change
flag and the `/change-password` guard, including an in-app attempt to reach Projects
through the brand link, then changes the password and reaches Projects. This navigation
must remain in-app: a full reload instead runs refresh, which intentionally rejects
pending-change users and requires another login. Required form labels include Naive UI's
asterisk, so credential locators match their label prefix. API response types come from
the generated schema.
Finally, the captured administrator token disables **only** the learner created by
this run, even after an assertion failure. The record remains in the dev database:
there is no delete API. An interrupted process or failed cleanup can leave an enabled
`e2e_` learner; an administrator must disable that specific account via User management.
Do not bulk-modify users or wipe the dev database to clean up these records.

Trace, video, and screenshots are off. Automatic error-context page snapshots are also
disabled via Playwright's `PLAYWRIGHT_NO_COPY_PROMPT` switch because the temporary-password
dialog contains a secret. Credential inputs avoid value-bearing `fill` call logs.
Do not enable debug/protocol logging, recording, or secret-bearing assertions when
running this flow. Normal Playwright reports/results remain gitignored.

## Test database

- The `test` command starts the in-memory SurrealDB container on 8101 if it isn't running.
- Each pytest session creates database `t_<worktree-short>_<random8>` in namespace `pandawords_test`
  and applies all migrations once. The database is removed at the end of the session.
- Tests isolate themselves by creating **fresh users** through factories. All user data is
  owner-scoped, and shared dictionary rows are deterministic and idempotent.
- Mark a test `@pytest.mark.fresh_db` when it needs an empty database (e.g. migration tests). It
  gets its own **unmigrated** database, removed after that test.
- The schema drift test applies the migrations to a fresh database and compares `INFO FOR DB`
  **and every `INFO FOR TABLE`** (including fields, indexes and events) with
  `backend/app/db/schema.snapshot.json`. JSON keys are sorted; schema definition strings are kept
  intact, and records, migration timestamps and random database names are not included.
- Normal test runs never rewrite the snapshot. Missing or changed snapshots fail with a unified
  diff (`committed` → `migrated`). Review the change, then run
  `.\scripts\dev.ps1 test -Backend -UpdateSnapshot` and commit the updated JSON alongside the new
  migration. The backend runner passes pytest's `--update-snapshot` flag explicitly.

## Fixtures

### Pronunciation audio (2.5.2)

`tests/unit/test_audio_sources.py` uses `httpx.MockTransport` for Commons metadata/downloads
and a fake Edge streaming client. It checks attribution, configured User-Agent, throttling,
redirect/host/MIME/size rejection, and voice selection without live external calls.
`tests/integration/test_audio.py` uses the isolated 8101 database and the actual registered
`run_once(..., settings=...)` dispatcher. It verifies source/fallback/missing-voice outcomes,
retryable versus unexpected failures, shared cache reuse across independently owned jobs,
private-cache exclusion, and effective-entry `pron.audio` references (including missing IPA).
Media test files retain the authenticated delivery/owner-isolation and safe-storage checks.
All new media test directories are created inside the worktree and removed on teardown.

Focused validation from `backend`:

```powershell
uv run --no-sync pytest -q tests\unit\test_audio_sources.py tests\integration\test_audio.py tests\unit\test_media.py tests\api\test_media_endpoints.py
```

Final fixture-backed E2E can use `AUDIO_NETWORK_ENABLED=false` on its API/worker processes;
audio jobs then complete as explicitly unavailable unless shared cached files already exist.
This does not fabricate audio or alter the add response. Live Wikimedia/Edge availability
and audio playback through production nginx are not claimed by the mocked backend suite.
### Enrichment worker (2.4.3)

`tests/integration/test_enrichment.py` exercises the registered `enrich` handler through actual
`run_once` claim/dispatch/completion, not a direct service substitute. Isolated migrated `job_db`
databases on the existing test server at 8101 cover semantic direction/type/source/owner,
frequency and exam-tag provenance, repeat processing, preserved user overrides/custom edges,
missing/private related endpoints, both derivation arrival orders, source-identity mismatch,
and retry/recovery after a missing artifact. Optional absence uses a production core-only build
of the synthetic fixture, without metadata mocks; its unique project-local artifact is removed
in `finally`. It asserts absence logging and retained existing metadata.

The reader's existing affix test also checks typed normalized/language-filtered reverse-root
lookup. Focused command from backend:
`uv run --no-sync pytest -q tests\integration\test_enrichment.py tests\integration\test_dictionary.py tests\integration\test_worker_live.py tests\unit\test_lexicon_reader.py`.
Migration `0010` adds optional lemma frequency/tag provenance and derivation source fields;
regenerate/compare the full schema snapshot using the normal backend runner.

### Add to project (2.4.2)

`tests/api/test_add_to_project.py` and `tests/integration/test_project_add_atomic.py`
cover authenticated new/repeat/subset/empty adds, exact selected senses, malformed and
foreign projects, invalid candidate selections, cross-user job access, preserved overlays,
hidden-membership restore without resetting timestamps, owner-scoped job deduplication
across projects, concurrent adds, terminal-job reuse and complete rollback after an enqueue
failure. They use the typed small lexicon and separate migrated `job_db` databases on the
existing test server at 8101 so shared deterministic dictionary fixtures cannot leak into
other tests. No external work or worker claiming is performed. Focused command from backend:
`uv run --no-sync pytest -q tests\api\test_add_to_project.py tests\integration\test_project_add_atomic.py`.

### Dictionary repository (2.2.3)

`backend/tests/integration/test_dictionary.py` uses the real migrated `db`, fresh users and
`lexicon_reader` small SQLite fixture. Run the focused suite from `backend` with
`uv run --no-sync pytest -q tests\integration\test_dictionary.py`.

It verifies explicit/default-common/empty selections, repeated/concurrent imports without duplicate rows or
edges, preserved custom content and overlays, invalid-selection preflight and transactional
rollback on shared-ID collisions. Owner-isolation probes cover foreign edges with shared
endpoints, shared/own edges to foreign endpoints, private parent lexemes and direct/batch/
incoming/outgoing reads. Shared records remain visible; applying nested requester overrides
neither changes shared data nor exposes identity/ownership fields. Affix composition and
directional semantic edges are idempotent and do not recursively materialize related senses.
The existing server on 8101 is reused; no dev database or server lifecycle changes are needed.

### User dictionary API (2.3.3)

From `backend`, run `uv run --no-sync pytest -q tests\api\test_overrides.py
tests\api\test_user_dictionary.py tests\api\test_notes.py`. These tests use fresh users and
the migrated, randomly named harness database on the existing test server (8101).

Coverage includes authenticated effective lemma entries; own custom sense/edge creation and
foreign-parent rejection; override application, recursive map patches, full replacement,
per-field reset by replacement and idempotent whole reset on all seven target tables; note CRUD
and current-target visibility checks after ownership changes/deletion. Every new route has
unauthenticated coverage and cross-user isolation (including administrator requests).
Shared rows/edges are compared before/after,
and invalid IDs, unknown/identity/pointer fields, wrong-table fields, nulls, invalid nested
values and strict rank/boolean validation are rejected. Shared `run` materialization explicitly
selects only `run-move`, preserving the existing repository test's initial-cache assumptions.
No memberships/add-to-project behavior or E2E/dev lifecycle is exercised here.

Verification on 2026-11-14: generated API contracts preserve every existing route/model;
`check` passed, the final backend suite passed **516 tests** and frontend unit tests passed
**85 tests**. The focused API suite passed **40 tests**. Initial missing `ruff`/`pytest` failures
were resolved with `uv sync --frozen`; frontend execution restored its locked cached packages.
The first full run exposed the shared `run` cache assumption described above; narrowed fixture
selection fixed it. The existing Starlette/httpx deprecation warning remains. Pylance could not
attach the worktree file; CLI basedpyright and runtime tests passed. Subsequent check/gen-api
verification called the existing script implementations directly to avoid loading private
development environment files. No remaining blockers; E2E and memberships are out of scope.

- `db`: async WebSocket connection to the migrated session database, or the empty database for
  a `fresh_db` test. `test_settings` selects the same database; `session_db` and
  `session_db_settings` explicitly access the shared migrated database.
- `app`: a test-configured FastAPI application with its real lifespan running. `client` is an
  async httpx client using that application through `ASGITransport`.
- `make_user`: typed async factory (`UserFactory`) using the auth service and repository, with
  unique usernames/IDs and real salted argon2id hashes on every call. Accepts keyword overrides
  for username, password, role, disabled and must-change-password. Its default test password is
  `test-password-123`. Do not share a single user between tests. Test settings supply test-only
  signing/bootstrap credentials; they never change the private development environment file.
- Auth service integration tests cover rotation/reuse, concurrent refresh on independent server
  connections, family-only revocation (including other-user isolation), logout, expiry, disabled
  users, and repeated/concurrent startup bootstrap. Readiness tests use the migrated harness
  database and its exact teardown rather than leaving ad hoc databases behind.
- Auth schema integration tests use `fresh_db`, apply the real migrations, and exercise username
  and token-hash uniqueness, field constraints and rotation metadata against the test server.
  Their opaque test password hashes are schema inputs, not usable login credentials. Teardown
  removes exactly each generated database; no dev database or shared test rows are modified.
- `job_db` / `job_settings` give each worker integration test its own migrated random database,
  preventing another test's queued jobs from interfering with global worker scans. Job tests
  synchronize candidate reads on two independent WebSocket connections before the conditional
  UPDATE, check scheduled exponential retries and their terminal limit, and exercise LIVE
  CREATE/UPDATE, socket loss/resubscription, polling without LIVE, and cancellation task cleanup.
  API tests verify owner-only status reads (shared jobs are not public), malformed opaque IDs,
  password-change gating and disabled accounts. No production services are started.
- Run unit tests from the selected worktree; it needs that worktree's backend environment
  (`uv sync --locked`) and frontend dependencies (`pnpm install --frozen-lockfile`).
- Project CRUD API coverage is in `tests/api/test_projects.py` and
  `test_projects_cleanup.py`: defaults/full reads, persisted partial updates and whole-plan
  replacement, deletion/not-found, owner-only admin-style pagination/counts, invalid fields,
  strict plan validation and malformed/wrong-table rids. Every route requires enabled,
  password-changed authentication; cross-user GET/PATCH/DELETE return the same 404 even for an
  administrator. Cleanup tests retain shared/custom content, notes, overrides and both users'
  unrelated memberships, including hidden membership removal. A foreign-owned edge attached
  to the project produces 409 with no deletion, preventing implicit cross-owner edge cascades.
  Focused command from `backend`: `uv run --no-sync pytest -q tests/api/test_projects.py
  tests/api/test_projects_cleanup.py`. These use fresh users in the migrated harness database,
  never dev data or a server lifecycle change.
- `lexicon_small.sqlite`: about 50 words (polysemy: *run*, *bank*; phrase: *kick the bucket*,
  *give up*; US/UK: *schedule*, *tomato*; derivation: *decide → decision*). It is built by the
  production importer and ECDICT/frequency/OEWN enrichment hooks from the committed synthetic
  `backend/tests/fixtures/lexicon-small.*`, `lexicon-small-ecdict.csv`,
  `lexicon-small-oewn.xml` and `lexicon-small-frequency.json` sources. These original concise
  glosses and frequency values are test inputs, not extracts or authoritative lexical claims.
  `lexicon_reader` is a reusable pytest fixture returning the typed, async `LexiconReader`.
  Derivation uses the production Kaikki suffix-template importer: typed affix rows attach
  the normalized base `decide` and suffix `-ion` to the `decision` lexeme. Reader tests follow
  the base back to the source lemma/lexeme and verify ordered components and provenance;
  no test-only SQL inserts these fixture rows.
- The DeepSeek client is faked in tests by default. No network access in unit, integration or API tests.

### Rebuild and verify the small lexicon

From `backend`, with existing dependencies (no download or database service required):

```powershell
uv run --no-sync python -m scripts.build_fixture_lexicon
# Optional alternate output; never overwrite a production lexicon for a test.
uv run --no-sync python -m scripts.build_fixture_lexicon --output .dev\lexicon-small-rebuilt.sqlite
New-Item -ItemType Directory -Force .dev | Out-Null
uv run --no-sync pytest tests\unit\test_lexicon_reader.py --basetemp=.dev\lexicon-reader-tests -q
```

Default output is `backend/tests/fixtures/lexicon_small.sqlite`, regardless of working directory.
Commit updated source inputs and the rebuilt database together. The focused tests rebuild into
a worktree-local scratch directory and compare the complete logical SQL dump with the committed
artifact (including source checksums). They cover exact/inflected/phrase lookup, polysemy,
ranked/common senses, accents, translations, tags, frequencies, directional OEWN relations,
structured derivation components imported from source etymology templates,
missing/invalid databases and invalid record payloads. A read-only probe attempts a write on
the actual connection before the service sets `query_only`; concurrent reads preserve the
file's hash/mtime and leave no open Windows file handle or journal. No full lexicon is loaded.

### Candidate resolution and API (2.4.1)

From `backend`, run `uv run --no-sync pytest -q tests\unit\test_candidates.py
tests\api\test_candidates_endpoints.py`. API tests use the authorized isolated 8101 harness
and real auth, explicitly configuring `Settings.lexicon_path` to the committed small fixture.
They cover normalized exact lookup, inflections, phrase forms, unknown input, shared results
for two independent users, invalid/empty payloads, anonymous/invalid-token access,
password-change and disabled-user gates, plus missing/corrupt configured artifacts.
The response preserves structured IDs, bilingual sense content, common defaults and provenance.
Unit tests preserve multiple form-index candidates without duplication, and prove that cold
spaCy initialization and inference have no running request event loop. `walks` deliberately
has no fixture form-index row, so its successful `walk` result proves the real offline spaCy
fallback, rather than only testing the dictionary index. No model or LLM download occurs.

For fixture-backed add-word dialog/E2E wiring, set an absolute `LEXICON_PATH` in the
test-controlled API process environment, or pass `lexicon_path=fixture_path` when constructing
test `Settings`. Do not modify the private shared `.env.dev` or restart the shared dev stack
for unit/API verification. The default remains `LEXICON_DIR/lexicon.sqlite`.

## What to test

Focused development-command guards (no shared dev ports or private environment changes):

```powershell
pwsh -NoProfile -File .\scripts\tests\lifecycle.Tests.ps1
pwsh -NoProfile -File .\scripts\tests\quality.Tests.ps1
pwsh -NoProfile -File .\scripts\tests\check-failure.Tests.ps1
pwsh -NoProfile -File .\scripts\tests\test-backend.Tests.ps1
```

The process test starts real tiny Node trees through native, cmd and actual pnpm launchers,
exercises stale/reused-PID guards and a
crashing launcher, and verifies all owned descendants disappear. The check test creates and
removes its own lint-error fixture and asserts nonzero exit plus Ruff's full failure diagnostic.

- Test behavior that a change introduces or fixes, with a few focused cases including edge cases.
- Always test owner isolation for new user-data endpoints.
- Don't test constants, re-exports, trivial accessors, framework behavior or markup snapshots.
- Coverage is not a goal.

### Media storage and authorization

`tests/unit/test_media.py` exercises kind/MIME/accent validation, stored extension
agreement, traversal, header injection, Windows reserved paths and link containment.
`tests/api/test_media_endpoints.py` uses real migrated metadata and worktree-local
temporary media directories; it covers bearer authentication, shared/private assets,
cross-user isolation, independent target ownership, deleted targets, missing files,
corrupt metadata, safe redirect headers and persistence-failure file cleanup.
The focused command from `backend` is
`uv run --no-sync pytest -q tests\unit\test_media.py tests\api\test_media_endpoints.py`.
Regenerate the snapshot explicitly with `dev.ps1 test -Backend -UpdateSnapshot`, then
run the normal backend suite to verify the committed schema. These API tests inspect
the nginx redirect contract; they do not prove production nginx playback.
