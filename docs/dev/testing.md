# Testing

## Export, import and backup UI (6.1.6)

Vitest (mocked generated API client, both locales):
- `src/features/portability/ArchiveImportForm.test.ts`: client pre-check (extension, empty,
  size), project import with `auto`/`on`/`off` progress sent as `include_progress`, localized
  422/409/413 and unmapped `bundle.*` rejections with the failed stage and path-free problems,
  transport errors, retry with the same file and options, upload status and `AbortController`
  cancellation, the user-restore confirmation, on/off-only restore progress and an already
  restored backup. Requests target only `/api/projects/import` and `/api/me/restore`.
- `src/features/portability/downloads.test.ts`: project export and user backup downloads
  (safe file name, skipped-media notice, no URL shown), localized errors, retry, cancellation;
  the backup request carries no user id.
- `src/features/admin/AdminBackupPage.test.ts`: loading/empty/error states, create → poll →
  download, 409/404/failed-stage feedback, no restore control, and site-backup navigation shown
  only to admins. `src/app/router.test.ts` already proves the `/admin/backup` route guard.

E2E: `frontend/e2e/portability.spec.ts` (see [Portability E2E](#portability-e2e-616)).

## Site backup and restore (6.1.5)

Backend selectors:
- `tests/unit/test_site_backup_archive.py`: manifest/path/limit/checksum validation, exclusions,
  the schedule and CLI stdin `check`.
- `tests/integration/test_site_backup.py`: creates disposable databases on 8101 with generated
  names and uses tmp media and backup directories. It covers:
  - restore round-trip into a fresh isolated database plus media;
  - absence of the lexicon and secrets;
  - permissions (POSIX only);
  - refusal of a non-empty target, and `--replace`;
  - a failed database stage leaving media untouched;
  - scheduled runs with retention;
  - a failed backup keeping the previous one;
  - the concurrent lock and a stale lock.
- `tests/api/test_admin_backup.py`: 401/403 for non-admins on create/list/download, admin
  create/409/list/download sha256, 404 for unknown or unsafe names, and that there is no restore
  route.

Combined with `tests/unit/test_backup.py` and `tests/api/test_config.py`, 50 cases pass. The
`deploy/restore.sh` control flow (stage failures, nonzero exit) was smoke-tested with a stub
`COMPOSE` command under Git Bash. It has not been run against real Docker.
## Offline leases and synchronization (7.1.2)

Backend selectors: `tests/api/test_offline_review.py`,
`tests/api/test_exercise_attempts.py`, `tests/integration/test_offline_migration.py`,
`tests/integration/test_schema_snapshot.py`, `tests/integration/test_srs_reviews.py`.
The isolated 8101 run passed 40 cases: bounded/concurrent issuance, unchanged
lease reuse in the final minute, server timing/grading, duplicate/reordered
submission, durable receipt replay, stale/expired no-op scheduling and isolation;
fresh/upgrade/replay schema and snapshot checks are included.

Frontend: `src/features/study/offlineReview.test.ts` uses fake-indexeddb for
eight persistence, account/logout, storage failure/eviction, expiry, partial sync,
give-up and lost-grade/receipt-response regressions. Run existing study/auth/API
tests as well. `pwa/offline.spec.ts` uses real Chromium IndexedDB and both locales,
network disconnection, lost receipt response, retry, cache inspection and logout
deletion; run with `pwa.playwright.config.ts` after the production build.
The service worker still stores no API data. Native OS install remains simulated
by the PWA suite; offline authentication on a cold reload is intentionally unsupported.

The offline localization/auth cleanup adds foreground bytes. The initial JS
budget is explicitly revised by 500 bytes to **184,000** (under 180 KiB),
retaining all route/chunk/precache bounds. The measured final payload remains
below the pre-optimization PWA baseline (183,977 bytes); build enforcement is
not skipped. Storage implementation is loaded lazily from auth cleanup.

6.1.6 adds the settings and admin-backup routes plus the project import dialog.
Portability messages load lazily (`src/i18n/portability/`) and bundle-error
parsing stays in the feature, but the new lazy routes and shared Naive UI chunks
(modal, scrollbar split) still add about 1.1 KB to the foreground: measured initial
JS **184,978** and static JS **671,278**; the project page gains the export button
(**256,461**). Initial JS is explicitly revised to **185,500**, static JS to
**675,000** and project tree to **258,000**; all other bounds are unchanged.

## Security boundaries (7.1.3)

Run the unit rate-limit/logging and API `test_security_*` suites plus exercise-attempt
and Pixabay integration regressions against the isolated 8101 fixture. They cover
anonymous/per-user fixed-window boundaries, recovery, proxy spoofing, and independent
owner checks on projects, graph records/edges, content, media, jobs and review attempts.
Build the frontend, then run `.\scripts\test-security-proxy.ps1` with a locally
available API image (`-ApiImage`): this uses actual production nginx responses,
both locales, protected images, graph/reading flows, CSP enforcement, URL-log privacy,
and direct/trusted-ingress spoofing probes. It cleans up only its own containers.
Project export (6.1.2) and project import (6.1.3) isolation is covered by
`tests/api/test_project_export.py` and `tests/api/test_project_import*.py` (see below).
User backup/restore (6.1.4) isolation is covered by `tests/api/test_user_backup.py` and
`tests/api/test_user_restore_failures.py` (see below).

## Measured graph and bundle budgets (7.1.4)

Run `tests/integration/test_graph_performance.py` with `-s` against the isolated
SurrealDB 3.3.5 test server (Python 3.14.3). It alternates 40 baseline/optimized
runs per workload, checks exact authorized results and deterministic ordering for
both directions, depth zero and relation/node filters, and records EXPLAIN plans.
Fixtures contain 30 nodes/42 edges and the maximum 300 nodes/449 edges, plus
foreign nodes/edges and unrelated/dense foreign tags. On the local Windows/Podman
run, median/p95 milliseconds were 121.27/165.20 -> 53.36/70.84 (30 nodes)
and 455.40/545.82 -> 179.76/239.30 (300 nodes). Queries fell from 54 to 22.
These are local measurements, not server latency guarantees. The test enforces
at most 22 queries and a deliberately loose 2-second p95 ceiling.

`pnpm run build` emits the Vite manifest and runs `bundle-budget.ts`; it reports
all initial, route and individual chunk transfer bytes and separately the PWA
install precache. Compression models production nginx gzip level 1/minimum 1024
bytes. Bounds: initial JS 185,500 bytes, initial CSS 4,800, per-JS chunk 225,000,
all static JS 675,000, project tree 258,000, project graph 525,000, all words
485,000, login 215,000 and PWA precache 1,160,000. Missing budgeted routes fail.
Focused frontend regressions cover graph lazy-load failure/retry and analyzer
dependency accounting; run the existing graph/router/project suites as well.

## Optimizer execution evidence (7.1.5)

The Phase 7 closeout additionally executed the real optional py-fsrs 6.3.3
optimizer in its bounded subprocess with 512 eligible transitions across 16
synthetic cards: success with 21 finite, bounds-validated parameters. Focused
optimizer suites passed 36 cases and existing SRS/attempt regressions passed 70;
the release test script also verified the opt-in image build argument.

## Personal semantic relations (4.4.3)

Using the existing test DB on 8101:

```powershell
Set-Location backend
uv run --no-sync pytest -q tests/api/test_relations.py tests/api/test_graph.py tests/api/test_graph_bounds.py
Set-Location ../frontend
pnpm exec vitest run src/features/graph/SenseRelations.test.ts src/features/graph/GraphExplorer.test.ts src/features/words/LemmaDetailPage.test.ts --maxWorkers=2 --testTimeout=60000
```

The integrated selectors passed 34 backend and 16 frontend cases. Coverage includes all seven
relation types, self-links, malformed IDs and caller-injected ownership/provenance, hidden and
foreign endpoints, shared/foreign edge immutability, four concurrent retries, independent owner
identities and protected identity collisions. UI cases cover both locales, explicit target
selection, retained choices after failures, retry/removal confirmation and graph refresh.
`dev.ps1 check` passed. No migration or external provider is required.

## Installable static shell (7.1.1)

From `frontend`:

```powershell
pnpm exec vitest run src\features\pwa --maxWorkers=2 --testTimeout=60000 --reporter=dot
pnpm run build
pnpm run test:pwa
```

The focused unit tests exercise sanitized registration warnings, localized native-prompt and
choice failures, recovery from newer install events, early/unsupported events, dismissal, both
locales, standalone mode, cache isolation and worker lifecycle failures.
The Playwright command starts its own strict-port loopback preview on 4179 and an ephemeral
update fixture; neither uses the shared API or database. Set `PWA_TEST_PORT` to a different
unused port for parallel worktrees; an occupied port is never reused. Chromium checks its own
installability diagnostics, manifest/icon and precache integrity, credential-free precache
requests, mocked online login/routing, real offline shell loading, uncached private traffic,
keyboard focus/install/dismissal, failure feedback and narrow/wide layouts in both locales.
Failure checks also ensure login remains usable and a delayed failure does not steal focus.
A real worker update
rejects altered shell bytes, preserves the active version, waits for an old controlled tab, and cleans
only obsolete app caches after activation. Integrated real-stack authentication remains the
coordinator's separate regression responsibility.

Verification on 2026-11-15: the focused PWA/router/login/auth/preferences selection passed
**38 tests**; `dev.ps1 test -Frontend` passed with `VITEST_MAX_WORKERS=2`. Production build,
the **7 Chromium PWA tests** (`PWA_TEST_PORT=4181`) and `dev.ps1 check` passed. The build
retains the existing large-chunk warning. No shared service lifecycle or database reset was used.

## Reading and inline vocabulary (4.2.3)

Using the existing healthy 8101 server and random isolated database fixture, from `backend`:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost'
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'
uv run --no-sync pytest -q --basetemp=.pytest_reading tests\api\test_reading.py tests\api\test_content.py
```

From `frontend`:

```powershell
pnpm exec vitest run src\features\reading src\app\router.test.ts src\features\projects\AddWordDialog.test.ts --maxWorkers=2 --testTimeout=60000 --reporter=dot
```

Coverage includes complete source/Unicode preservation with unordered sentence input and gaps,
three occurrence states, effective definition/gloss overlays, no/hidden sense or ancestor
memberships, ambiguous candidates with explicit-only sense choice, unavailable content in both
locales, preserved ingestion/lookup drafts, dismissal, add/link failure and retry without repeating
a successful project add. Real API tests independently reject foreign passages, sentences and
project context; no cross-user content is embedded. The reading routes retain normal auth guards.

Verification on 2026-11-15: **10 backend tests passed**, **16 frontend tests passed**;
`dev.ps1 gen-api` and `dev.ps1 check` passed. Initial checks identified generated optional/tuple
typing, token classes, a fixture connection annotation and formatting; these were corrected.
A retry-test mock initially omitted the newly reloaded project page, causing two frontend test
failures; its response was corrected and the complete focused command passed. No provider,
migration, shared service lifecycle/reset, dependency symlink/junction, full suites or browser/E2E
run was performed; integrated browser validation is reserved for the main coordinator.

## Image review and review media preferences (5.1.3)

Against the already-running loopback 8101 server, from `backend`:

```powershell
uv run --no-sync pytest -q --basetemp=.pytest_image_regression tests\unit\test_exercise_image.py tests\unit\test_exercise_recall.py tests\unit\test_exercise_framework.py tests\api\test_image_review.py tests\api\test_review_preferences.py tests\api\test_recall_attempts.py tests\api\test_exercise_attempts.py tests\api\test_srs_preferences.py tests\integration\test_review_media_migration.py tests\integration\test_auth_schema.py tests\integration\test_srs_migration.py tests\integration\test_schema_snapshot.py
uv run --no-sync pytest -q --basetemp=.pytest_production_image tests\api\test_production_image_review.py
```

These passed **119 + 1 tests**. The production-registry test uses the same legitimate fixture
content as the browser: a mature `schedule` card, an answer-free local calendar image, private
empty definition/gloss/examples, disabled audio and disabled LLM. Thus only image recall is
eligible without altering production selection, adding a force-type endpoint or depending on RNG.
Other cases cover exact target/owner, stable multiple-image selection, actual file-byte decode,
missing/corrupt/deleted media, encoded attribution leaks, normalized selected forms, wrong/give-up
answers, migration/replay/defaults, partial preferences, accent, isolation and already-issued
image/audio grading after toggles. Existing weights and new/learning recognition are retained.

From `frontend`, the affected regression run passed **73 tests**:

```powershell
pnpm exec vitest run src\features\study src\features\words\SenseImages.test.ts src\features\words\MnemonicNotes.test.ts src\features\admin\AdminUsersPage.test.ts src\features\auth --maxWorkers=2 --testTimeout=60000 --reporter=dot
pnpm exec playwright test image-review.spec.ts --list
```

`dev.ps1 gen-api`, `dev.ps1 check`, production `pnpm run build`, browser-test TypeScript
compilation and browser collection passed. Snapshot regeneration used the existing
`--update-snapshot` option and subsequent comparison passed. Initial checks caught and corrected
formatter/import issues, new required auth-fixture fields, an incorrectly nested frontend test,
a misplaced decoder-error callback and a non-token spacing step. The migration test exposed
the simultaneous-bool-backfill requirement recorded in `surrealdb-notes.md`.

The browser selector is **`image-review.spec.ts`**, test name
**`fixture image review authenticates blobs, persists preferences and confirms exactly once after retry`**.
Run it against the coordinator's integrated fixture-backed dev stack with `LLM_DAILY_BUDGET=0`,
`AUDIO_NETWORK_ENABLED=false`, the existing admin credentials and dev DB connection environment:

```powershell
pnpm exec playwright test image-review.spec.ts
```

It creates/disables its own `e2e_image_*` learner and removes its own image/project, completes
mandatory password change, exercises keyboard toggles/accent and both preference states, verifies
real authenticated calendar pixels after a failed delivery/retry, deletes/reloads the issued
image, answers via Enter and retries a confirmation whose first response was lost **after** the
server persisted it. The receipt and daily review count remain exactly one across reload.
`backend\scripts\seed_image_review.py` only matures the named isolated learner's fixture card
in a loopback development database; no HTTP/runtime test bypass exists. Frontend tests separately
verify both locales, unavailable/retry states and object-URL revocation on decode failure/unmount.
The branch did **not** execute the browser against the shared main-source stack or perform any
8100 migration/service lifecycle/reset operation; final integrated browser execution is deferred
to the coordinator. Full backend/frontend suites were not run.

## Context-aware recall and distractors (4.4.4)

With the existing healthy test DB on 8101, from `backend`:

```powershell
uv run --no-sync pytest -q tests\unit\test_cloze_context.py tests\unit\test_exercise_recall.py tests\unit\test_distractors.py tests\integration\test_context_cloze.py tests\integration\test_context_distractors.py tests\integration\test_distractor_graph.py tests\api\test_context_attempts.py tests\api\test_recall_attempts.py
```

Tests cover original Unicode code-point offsets (emoji, NFKC expansion, combining characters),
all repeated/inflected forms, owner-private versus source example precedence, hidden/deleted
links/endpoints, stale spans, bounded discovery and missing-context fallback. Real DB/API tests
authorize both sentence and edge owners, deny foreign attempt access, retain no-store prompt
responses, and leave the shared LLM cache unchanged. They verify server grading, no SRS write
before confirmation, one owner-scoped receipt/log on confirmation and idempotent retry.
Tag/morph tests cover each relation/endpoint owner, tier precedence, bidirectional synonym
exclusion, deterministic seeded ordering, bounded choices and insufficient-safe-choice fallback.
No provider, new migration, frontend change or generated API shape is needed.
Context tests that add study data use isolated job databases, so their enrichment jobs
cannot displace unrelated worker tests in the shared session database.

Integrated regression fixtures must clear the fixture's `zh` gloss explicitly: an empty gloss
object preserves existing translations under the effective-record recursive merge. Both the API
and browser image-only fixtures use an empty `zh` value so recognition cannot become eligible.
Mnemonic API tests use their own migrated job databases instead of draining other tests' queued
jobs. The pre-0018 migration probe inserts a historical user record without post-0020 preference
fields. After these integration corrections, the three affected backend files passed **19 tests**.
The browser selects the Naive UI accent radio with keyboard focus and Space, avoiding a direct
click on its visually overlaid native input while exercising the accessible control.
Authenticated delivery is checked against the server's current user, not equality with an older
access token: normal route reloads can refresh credentials. Assertions never print bearer tokens.
Integrated image-review execution on 2026-11-15 passed against the real loopback dev stack:
authenticated pixels, unavailable/retry after deletion, persisted media preferences and exactly
one durable confirmation receipt all passed. The closeout tree's full backend suite passed
**1095 tests** (one existing Starlette warning). Browser-test lint and `tsconfig.node.json`
type-checking passed. No provider requests, service resets or shared-resource cleanup were needed.

## Phrase discovery and normal add flow (4.1.2)

Using the existing healthy 8101 server, from `backend`:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost'
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'
uv run --no-sync pytest -q --basetemp=.pytest_phrase_flow tests\api\test_phrases.py tests\api\test_add_to_project.py tests\api\test_candidates_endpoints.py tests\integration\test_phrase_materialization.py
```

From `frontend`:

```powershell
pnpm exec vitest run src\features\words\ContainingPhrases.test.ts src\features\projects\AddWordDialog.test.ts src\features\words\LemmaDetailPage.test.ts --maxWorkers=2 --testTimeout=60000 --reporter=dot
```

Cases cover exact graph components, deduplication, stable pagination/bounds, invisible
endpoints/edges/ancestry, authentication, missing targets and no matches. A two-sense phrase
fixture proves explicit-only selection and unchanged memberships/FSRS cards after a real
review and repeat/cross-project adds. Frontend cases exercise composition wording, exact
phrase navigation, project choice, ordinary candidate search/selected-sense add, and both
locales' loading/empty/error retry states. OpenAPI generation uses `dev.ps1 gen-api`.

Verification on 2026-11-14: the focused backend command passed **11 tests**, the frontend
command passed **15 tests**, `dev.ps1 gen-api` completed and `dev.ps1 check` passed.
Initial test-only fixture omissions, an async-generator assertion, incomplete API mocking
and unsupported nested `setProps`/button selectors were corrected before these passing runs.
The initial quality check caught formatting and was rerun successfully after formatting.
Full backend/frontend suites and browser/E2E were not run for this isolated task; the
coordinator performs integrated validation. No service lifecycle/reset, migration, external
LLM or dependency junction/symlink operation was performed.

## Private sentence/passage ingestion (4.2.2)

Using the already-running loopback 8101 server and random isolated database harness, from backend:

```powershell
uv run --no-sync pytest -q tests\unit\test_content_analysis.py tests\api\test_content.py
```

The small offline lexicon covers inflections, repeated words, ambiguous and unmatched occurrences.
Tests exercise Unicode/punctuation/combining-character spans and exact whitespace preservation,
CRUD/auth/admin cross-user isolation, pagination and malformed spans, ordered/reused sentences,
retry-safe manual resolution, foreign-owned/mismatched-endpoint associations, passage deletion
without sentence deletion, and injected mid-ingestion rollback. Optional unavailable/invalid
LLM results use mocks and check private owner input scope and candidate/span validation.
Concurrent retry and manual part assignment/removal cases preserve repeated-sentence order and
original offsets even when an association is removed. Foreign-owned incident edges fail deletion
closed (409) because the database would otherwise cascade them.
No live provider or service lifecycle command is needed. Generated contracts are refreshed by
`dev.ps1 gen-api`; `dev.ps1 check` validates both stacks.

Verification on 2026-11-14: API generation and `dev.ps1 check` passed; the final focused content
suite plus the migration-replay regression passed **31 tests in 10.94 seconds**. The wider
content/context/dictionary run had **106 passed, 1 setup error** (existing 2-second DB transport
timeout); that exact migration-replay case passed in the final retry. A full backend run was
interrupted at coordinator request in favor of one integrated main-branch run; it is not a pass.
No live provider, frontend/E2E execution, migration or service lifecycle operation was performed.

## Private image attachments (5.1.1)

Against the existing loopback 8101 server, from `backend`:

```powershell
uv run --no-sync pytest tests\unit\test_image_validation.py tests\api\test_image_endpoints.py tests\integration\test_pixabay.py -q
```

Fixtures use a random migrated database and per-test media directories under the worktree.
Provider calls are mocked: no live Pixabay requests or keys are required. Tests cover supported
decoders, malformed/spoofed data, encoded/pixel/animation limits, private/shared/foreign senses,
concurrent retries, conflicting identities, removal/missing files and persistence rollback.
Provider tests cover owner caches, result identity selection, attribution, local worker storage,
disabled search, empty results, throttling, host/redirect checks, timeout and oversized bodies.
Frontend: `pnpm exec vitest run src\features\words\SenseImages.test.ts
src\features\words\LemmaDetailPage.test.ts --maxWorkers=2 --testTimeout=60000`.
Nginx's 11 MiB allowance is configuration coverage; a deployed-proxy near-limit smoke test
requires the deployed nginx stack and is not implied by the in-process API tests.
`scripts\test-image-proxy.ps1 -ApiImage <local-api-image>` now provides that separate,
isolated container regression using the actual production nginx configuration. Fresh empty
Podman media volumes must remain API-owned after nginx mounts them; the API image's
initialization marker prevents a second empty-volume copy-up from replacing ownership.

## Bounded graph API (4.4.1)

From `backend`, against the existing healthy loopback **8101** server:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost'
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'
uv run --no-sync pytest -q --basetemp=.pytest_graph tests\api\test_graph.py tests\api\test_graph_bounds.py
```

These tests exercise the real authenticated router and migrated isolated database, not mocked
traversal. They cover all seven node types/nine relations, effective overrides, depth/direction,
stored orientation, isolated focuses, deterministic ordering, malformed IDs, hidden ancestors,
project union, own records without selections, foreign edges/endpoints and unselected shared
neighbours. Bounds tests accept exactly 300 nodes, reject 301 without partial output, and reject
a 101-node complete graph containing 10,201 edges. Instrumentation counts real query responses:
at most 55 reads per measured request, at most 10,001 rows per read, and bounded aggregate rows.
Depth reduction succeeds after rejection. Dense fixture writes are batched to fit the harness's
two-second query deadline. No shared service lifecycle or migration change is required.

Verification on 2026-11-14: the graph suites plus dictionary/project-tree regressions passed
**30 tests in 30.63 seconds** (22 graph cases). `dev.ps1 gen-api`, `dev.ps1 check`,
`dev.ps1 test -Frontend`, and `git diff --check` passed. The frontend runner prints only
`Selected tests passed`, not a case count. No full backend suite or E2E run was performed;
the coordinator runs integrated suites. Initial worktree Ruff absence was resolved with
`uv sync --frozen --quiet`; generation restored its own local locked frontend tools.
Initial fixture schema/SDK assumptions, the boolean parser form and dense seed query timeout
were corrected before the final clean runs. No dependencies were symlinked.

## Mnemonic notes and optional suggestions (5.1.2)

Against the existing loopback **8101** server (each pytest process uses an isolated random DB):

```powershell
cd backend
$env:NO_PROXY = '127.0.0.1,localhost'
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'
uv run --no-sync pytest -q tests\api\test_mnemonics.py tests\integration\test_mnemonic_context.py tests\api\test_notes.py tests\api\test_jobs_endpoints.py tests\integration\test_llm.py tests\integration\test_jobs.py --tb=short
cd ..\frontend
pnpm exec vitest run src\features\words\MnemonicNotes.test.ts src\features\words\LemmaDetailPage.test.ts --maxWorkers=2 --testTimeout=60000
cd ..
.\scripts\dev.ps1 gen-api
.\scripts\dev.ps1 check
pnpm --dir frontend build
```

Real note/suggestion API and worker tests use an in-process mocked OpenAI transport, never live
DeepSeek. They cover all three target tables, note-kind preservation, explicit-save-only behavior,
private targets/jobs/cache, canonical visible ancestry, excluded notes/overrides, changed/deleted
targets, malformed/oversized/markup output, disabled/timeout/provider failures, real budget
exhaustion and retry. UI tests cover both locales, separate suggestions, accept/edit/save,
replacement confirmation, reject/cancel, polling, late target/user responses, failed requests,
tab-draft restoration and storage/offline fallback. These are isolated API/component tests,
not live-provider or real-stack browser verification. No service lifecycle operation is needed.

Verification on 2026-11-14: **58 backend cases passed**, **22 frontend cases passed**;
`gen-api`, final `dev.ps1 check`, production frontend build and `git diff --check` passed.
The first check failed because worktree-local Ruff was absent; `uv sync --locked` and
`pnpm install --frozen-lockfile --silent` restored local locked dependencies (no symlinks).
Initial test-only login failures came from replacing the test application's signing settings
with unrelated defaults; using a copy of the isolated test settings fixed them. Intermediate
format/lint failures were corrected before the final clean check. No full backend/frontend
suite, E2E, live-provider call, migration or development-stack lifecycle action was performed.

### Evidenced morphology (4.3.2)

Run from `backend`: `uv run --no-sync pytest tests\integration\test_morphology.py
tests\unit\test_lexicon_affixes.py -q --basetemp=.pytest-morphology`.
The offline builder tests template aliases, normalization, diagnostics, conflicts, source
order and repeats. Real random databases on the existing 8101 server verify shared IDs,
provenance, repeated-component edges, insert-only retries/conflicts, owner-filtered
composition/group reads and LLM failure/rejection without guessed records. The integration
fixture is built through the production pipeline and includes explicit root/affix identities.
The committed general lexicon is rebuilt as schema v3; its missing `-ion` mapping intentionally
remains unanalysed. No service restart or live user database reset is needed.

## Sentence and passage schema contract (4.2.1)

From `backend`, with the existing healthy loopback **8101** test server:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost'
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'
uv run --no-sync pytest -q tests\integration\test_context_schema.py tests\integration\test_dictionary_schema.py tests\integration\test_schema_snapshot.py tests\integration\test_migrations.py
```

The focused suite uses isolated random databases, not the persistent dev database. It covers
fresh migrations, no-op and direct 0005 replay over populated context graphs, committed snapshot
comparison and readable synthetic drift. Typed endpoint unions/existence, shared/private owner
fields, required context fields, multilingual translations, unknown fields, optional exact
integer-pair spans and required integer passage order are exercised against real SurrealDB.
Explicit mismatched-owner edge probes demonstrate that ENFORCED endpoints and an edge-owner
filter alone do not provide authorization; later CRUD/reading tests must check both endpoints.

Verification on 2026-11-14, SurrealDB **3.3.5**: **89 focused tests passed**, including **30**
new context cases, and `dev.ps1 check` passed. The existing schema is sufficient, so migration
0005 and the snapshot remain unchanged. The initial check could not find worktree-local Ruff;
`uv sync --frozen --quiet` restored locked backend dependencies before rerunning successfully.
An initial SCHEMAFULL probe incorrectly expected unknown fields to be dropped; the real server
rejected them, and the test now asserts that observed contract. The Pylance syntax tool timed
out; actual pytest, Ruff and basedpyright provide validation instead. No API shape changed,
so API generation is not needed. No frontend/E2E or stack lifecycle operation was performed.
The additional `dev.ps1 test -Backend` run finished with **923 passed, 1 failed, 1 warning**
in **519.35 seconds**: the unchanged
`test_llm.py::test_valid_persistent_canonical_cache_disabled` hit its mocked-provider timeout.
Its immediate isolated retry passed (**1 passed in 1.86 seconds**); the full run is not a clean
pass. No unrelated LLM test or production behavior was changed.

## Phrase lexicon and shared composition (4.1.1)

From `backend`, against the existing isolated random-database harness on loopback **8101**:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost'
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'
uv run --no-sync pytest -q --basetemp=.pytest_phrase tests\unit\test_lexicon_phrases.py tests\unit\test_build_lexicon.py tests\unit\test_lexicon_reader.py tests\unit\test_candidates.py tests\integration\test_phrase_materialization.py tests\integration\test_dictionary.py
```

The production-built synthetic fixture now has 56 lemmas/58 input records and SQLite schema v2;
rebuild older artifacts with `python -m scripts.build_fixture_lexicon` (no network required).
Phrase cases cover ordered/repeated component identities and provenance, source-order-independent
builds, exact phrase versus inflected word lookup, missing words, POS/etymology ambiguity,
conflicting/foreign/markup/oversized templates and no inferred whitespace decomposition.
Separate idiomatic meanings and explicitly tagged literal examples exercise `contains` versus
`used_in`; unlabelled examples do not create usage links. Real graph tests cover repeat and
concurrent materialization, repeated-component positions, unchanged shared/private content,
shared graph visibility and independent edge/endpoint owner filtering.

Verification on 2026-11-14: `dev.ps1 check` passed; the final focused run passed 63 cases,
and 106 additional lexicon affix/ECDICT/OEWN/release, dictionary schema and candidate/add API
regressions passed. The focused run includes repeated-component concurrency and
oversized-template cases. The initial check failed
because worktree-local Ruff was missing; `uv sync --frozen --quiet` restored locked dependencies.
Subsequent line-length, import-placement and a test-only unhashable-JSON type finding were
fixed before the final passing check. Pylance's syntax MCP
request timed out; executable imports/tests, Ruff and basedpyright provided validation.
No new API, migration, frontend/E2E or full backend suite, external LLM, shared database reset,
dependency symlink/junction or development-stack lifecycle operation is part of this task.

## Hierarchical tags (4.3.1)

Against the already-running isolated loopback 8101 harness, from `backend`:
`uv run --no-sync pytest -q tests\api\test_tags.py tests\integration\test_tag_migration.py tests\integration\test_schema_snapshot.py`.
The real API/database cases cover owner/shared CRUD, strict fields/kinds/names/IDs, all three
assignment target tables, independent endpoint and edge ownership, cross-user access including
admin, duplicate assignment/removal retries, concurrent opposing parents and duplicate writes,
multi-level cycles, rollback on delete failure, cleanup, and fail-closed foreign-edge protection.
Migration 0018's schema is included in the committed snapshot.

From `frontend`: `pnpm exec vitest run src\features\tags src\features\words\LemmaDetailPage.test.ts --maxWorkers=2`.
Mocked UI tests cover bilingual create/assign/remove/restore, immutable source memberships,
preserved drafts and selections on API/network failures, loading/empty/retry/cycle feedback,
rename and confirmed deletion conflicts. These are not real-stack browser tests.
Final focused results: **38 backend tests passed** (tag API, existing-user migration backfill,
notes/overrides regressions and schema snapshot) and **13 frontend tests passed** (tag widgets/page
plus word-detail regression). `dev.ps1 gen-api` regenerated contracts; final `dev.ps1 check` passed.
Initial fixture/selector/typing failures were corrected; no full backend/frontend suite,
E2E, LLM or network audio check is implied. Existing shared services were neither restarted
nor reset; the 8100 syntax probe cleaned only its unique scratch records.

## Project review session (3.3.2)

`frontend/src/features/study/ReviewSessionPage.test.ts` exercises recognition IDs, generic typed
recall/scenario prompts, server-owned hints/unavailable hints, give-up, manual Easy, receipt-only
progress and exhaustion, empty/loading, no-usable/stale/expired/unavailable/recoverable errors,
duplicate protection, exact-body retry, refresh recovery, storage failures, protected-audio
failure, navigation confirmation, owner scoping and both locales.
`useReviewSession.test.ts` additionally verifies uncertain confirmation recovery, non-receipt
responses, progress refresh failure after confirmation, and invalidating late owner/disposal
responses. These are mocked frontend tests, not real-stack browser verification.

Run `./scripts/dev.ps1 test -Frontend`, `./scripts/dev.ps1 check`, and `pnpm --dir frontend build`.
For the separate real-stack E2E task, open a project's review link, select a choice (or type in
the labelled input), submit, inspect server feedback, optionally select `[data-rating="easy"]`,
then confirm. Wait for a new `review-exercise` attempt ID or `review-empty` only after a receipt,
reload, and verify persisted queue/progress. See the review-session browser selectors in
`docs/ui/patterns.md`; no external LLM or audio availability is required.

The token-enforcement suite initializes the ESLint configuration in a dedicated 60-second
setup hook. This keeps cold plugin/configuration loading out of the first assertion's
20-second budget; normal frontend tests need no retry or temporary timeout edits.
The full design-preview App integration test uses a scoped 20-second budget because it
mounts both complete theme catalogues, including six exercise shells, and switches locale.

Concrete exercise API tests inject a focused registry through the API's request-bound
factory when asserting a particular exercise. Additional recognition lifecycle cases use
the production bootstrap without overrides. Distractor graph tests use isolated migrated
databases so equal-frequency candidates from other suites cannot change seeded choices.

## Recognition plugins (3.2.3)

From `backend`, using the existing isolated random-database harness on loopback **8101**:

```powershell
uv run --no-sync pytest -q tests\unit\test_recognition.py tests\integration\test_recognition_graph.py tests\api\test_recognition_attempts.py
```

These suites register the real plugins explicitly without depending on application bootstrap
ordering. They cover all three exercise types, effective selected senses/overrides and Chinese-gloss
fallback, optional pronunciation, opaque unique options, correct/wrong/give-up grading, missing
relations/alternatives and registry fallback. Real graph tests cover both directions of semantic and
derivation edges, competing valid answers, bidirectional synonym exclusion, private edges/endpoints/
ancestry and another owner's overrides. Real HTTP attempts verify no answer keys before grading,
all attempt operations' owner isolation, Good-capped automatic ratings and persisted manual Easy.
No LLM, frontend/E2E run, migration or development-stack lifecycle operation is needed.

Verification on 2026-11-14: `dev.ps1 check` passed; **126 distinct focused/framework/distractor
regression cases passed**. The existing frequency-tier graph case was verified separately:
in a combined run, earlier shared same-frequency fixtures can displace its randomly named
candidate from the top four (125 passed, one assertion failed); its isolated run passed.
Pylance hover timed out; executable tests, Ruff and basedpyright provided validation.

## Distractor provider (3.2.2)

From `backend`, against the existing isolated-database test server:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost'
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'
uv run --no-sync pytest -q tests\unit\test_distractors.py tests\integration\test_distractor_graph.py
```

Pure tests cover all ranking tiers, frequency floor boundaries and unknown frequencies,
missing POS/graph data, synonym IDs and labels, Unicode/case/whitespace display deduplication,
choice-count bounds, insufficiency and seeded reproducibility. Real migrated database tests
exercise each Phase 2/optional tag tier, reverse semantic relations, foreign private senses,
tags and ancestry/semantic edges, own private candidates, effective override isolation,
duplicate definition labels and oversized synonym safety sets. No migration, live LLM,
recognition registry changes, E2E or stack lifecycle operation is needed.

Verification on 2026-11-14: **98 tests passed** across the distractor suites and existing
exercise framework/state/API regression suites; `dev.ps1 check` passed. A Pylance syntax
request timed out; actual imports/tests, Ruff and basedpyright supplied validation instead.
Missing worktree Python dependencies were restored with offline `uv sync`, without changing
manifests. No full backend suite or E2E run is implied by this focused result.

## Plan and dashboard UI (3.3.3)

Focused command from `frontend`:
`pnpm exec vitest run src\features\study src\features\projects\ProjectEditorPage.test.ts --maxWorkers=2`.
Tests cover complete project-plan preservation, optional-field clearing, zero limits,
validation and save failures; separate desired-retention validation/PATCH without card/history
writes; past/impossible/buffer-at-risk exams; loading, no-history versus true 0% retention,
empty queues/projects, bilingual API/transport failures and review/plan navigation.
Priority tests load multiple tree pages, include visible senses outside a zero-capped queue,
exclude hidden ancestors, block partial-load saves and retain drafts on selection conflicts.
The priority editor deliberately declares its tree-order initialization: the current API has
no read endpoint for the full saved priority.

Verification on 2026-11-14: `dev.ps1 check` passed, and the final full frontend suite passed
**126 tests** with
`pnpm exec vitest run --maxWorkers=2 --testTimeout=60000 --retry=1 --reporter=dot`.
The production build (`pnpm build`) passed. The normal `dev.ps1 test -Frontend` run encountered
three existing App/token-enforcement wall-clock timeouts under shared-machine load; the
serial run passed 125 tests but still hit the token suite's explicit 20-second first-test
timeout. An isolated retry confirmed that explicit timeout is not overridden by the CLI's
60-second default. The final retry-enabled run accommodates ESLint's cold initialization
without changing unrelated test files. The first check lacked worktree-local `ruff`; restoring
the existing locked dependencies with `uv sync --frozen --quiet` resolved it. ESLint formatting
findings were fixed before the passing final check. No backend tests, E2E, generated-contract
edits, stack lifecycle operations or live-data changes were performed for this frontend task.

## Cloze and listening recall (3.2.4)

On the existing loopback 8101 server, from `backend`:

```powershell
uv run --no-sync pytest -q tests\unit\test_exercise_recall.py tests\api\test_recall_attempts.py tests\unit\test_exercise_framework.py tests\api\test_exercise_attempts.py
```

Pure cases cover selected inflections, normalized Unicode/case/whitespace/punctuation,
whole-word and multiword blanks, invalid examples, all-answer-occurrence removal, strict
listening spelling, and independent fallback to recognition. Migrated API cases explicitly
schedule introduced **Review** cards (new/learning cards must still select recognition),
then exercise real create/read/answer/give-up/confirm flows and pregrade answer-key exclusion.
They store local synthetic media bytes, exercise both accent preferences and authenticated
delivery, reject private/wrong-target/wrong-accent/missing files and changed headword spelling,
and verify that grading alone creates no review log. Media scratch directories live inside
the worktree and are removed after each test; no live audio/LLM calls are needed.
The framework's existing owner-isolation and replay tests remain in the focused command.

Verification on 2026-11-14: all **77 focused recall/framework tests passed**. The complete
repository `dev.ps1 check` passed. The complete backend run had **781 passed, 1 failed**: the unchanged
`test_valid_persistent_canonical_cache_disabled` hit its five-second mocked-provider timeout
on the first SDK call; adding that test to the focused retry reproduced the same timeout
while all 77 exercise tests passed. This is not a clean full-suite pass. No provider network
traffic is involved in that LLM fixture. Pylance's worktree hover request timed out; actual
runtime tests and basedpyright checked the plugin contracts instead. Missing worktree test
dependencies were restored with `uv sync` after the initial no-sync runner could not find
pytest. No schemas, migrations or API transport shapes changed, so gen-api was not needed.
No E2E, stack lifecycle or persistent dev-database operations were performed.

## Daily plan and dashboard (3.1.3)

From `backend`, with `SURREAL_TEST_URL=ws://127.0.0.1:8101/rpc` and loopback proxy bypass:
`uv run --no-sync pytest -q tests\unit\test_study_plan.py tests\api\test_daily_plan.py
tests\api\test_plan_statistics.py`.

Pure tests cover exact exam suggestion/capacity, zero limits, passed/today instants, future
midnight versus 00:01, offset-aware local midnight and the separate buffer deadline;
deterministic FSRS retrievability/fallback ordering, completed allowances, actual seven-date
forecasts, UTC retention boundaries, streak endings and shared-card capacity allocation.
Real migrated API fixtures cover empty projects, auth/cross-user access on all endpoints,
pagination bounds, full plan replacement, persistent reorder/hidden slots and timestamp
preservation, hidden ancestors, content/edge/membership owner isolation, shared cards reviewed
in different projects, zero/unlimited/exhausted limits, UTC reset, history isolation and legacy
reconciliation without introduction. Migration `0016` participates in snapshot generation and
normal drift/replay checks. Pylance could not resolve this worktree's new file; actual runtime
tests, basedpyright and Ruff provide validation instead.

Verification on 2026-11-14: full backend snapshot-update suite passed **689 tests**; final
normal focused planning/schema/migration/SRS-limit suite passed **46 tests** (29 planning
cases). `dev.ps1 check` and `gen-api` passed. The standard frontend runner twice timed out the
existing token-enforcement test at 20 seconds; the unchanged full suite passed **109 tests**
with `pnpm exec vitest run --reporter=dot --maxWorkers=1 --no-file-parallelism`.
An initial quality run caught typed tree-table fixture arguments; another overlapped the
backend migration tests' temporary probe files and linted them before their automatic cleanup.
The final quality run after suite completion was clean. Initial focused collection used
duplicate test module basenames; unique names fixed collection. An ownership fixture initially
changed a different lexeme edge; selecting the actual ancestry fixed the probe.
Missing worktree dependencies were restored through `uv sync` and the API generator's pnpm
install, without manifest changes. The existing Starlette/httpx warning remains. No E2E,
stack lifecycle operations, persistent dev-DB mutation or unrelated changes were performed.

## Exercise framework and attempts (3.2.1)

From `backend`, using the existing healthy isolated-database server:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost'
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'
uv run --no-sync pytest -q tests\unit\test_exercise_framework.py tests\integration\test_exercise_state.py tests\api\test_exercise_attempts.py tests\integration\test_schema_snapshot.py
```

Typed offline fake plugins exercise the registry before the later production generators exist.
Coverage includes new/Learning/Relearning, exact seven-day kind weights independent of type
counts, one eligible kind, explicit skip/no-usable reasons, deterministic normalization and
selected effective forms with owner-overlay isolation, and listening's narrower audio-form rule.
Real migrated database/API tests check no pregrade answer-key/correctness leakage, all owner
boundaries, hints, correct/wrong/giveup, immutable submission retries, concurrency, manual final
ratings, durable receipts and crash recovery between the SRS and attempt-confirmation commits.
They also check hidden lemma/lexeme/sense, removed membership, deleted project, expiry, stale
issuance versions, invalid durations and server-elapsed/60-second caps. Failed operations leave
memory and review history unchanged.

Regenerate the schema explicitly with the snapshot test's `--update-snapshot`, then compare
normally. `dev.ps1 gen-api` regenerates OpenAPI and TypeScript; `dev.ps1 check` checks both stacks.
No live provider, E2E, stack lifecycle operation or dev-database mutation is required.

Verification on 2026-11-14: focused exercise + schema comparison passed **67 tests**;
the final complete backend run passed **725 tests**
with the existing Starlette/httpx deprecation warning. API generation and `dev.ps1 check`
passed. The default frontend runner twice timed out the existing token-enforcement test's
20-second budget (108 passed); the unchanged suite passed **109 tests** with
`pnpm exec vitest run --reporter=dot --testTimeout=60000`. No timeout setting was committed.
Initial pytest collection exposed duplicate API/integration module basenames; the integration
test was renamed. Pylance cannot resolve this new worktree's file URI; Ruff, basedpyright and
real runtime tests validate the implementation instead.

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

## Scenario recall (3.2.6)

From `backend`, run `uv run --no-sync pytest -q tests\unit\test_exercise_scenario.py
tests\integration\test_scenario.py tests\integration\test_scenario_contracts.py`.
These use the existing isolated 8101 harness and a real OpenAI SDK with `httpx.MockTransport`;
no live provider, dev database, E2E or stack lifecycle operation is needed.
Fake registry types independently verify fallback selection and local accepted-form grading.
Coverage includes strict/malformed/answer-leaking JSON, Unicode and separated-spelling leaks,
nonblocking misses, concurrent deduplication and worker claims, validated disabled/zero-budget
cache reuse across shared owners, prompt-version invalidation, private overlay/custom scopes,
note exclusion, stale content, terminal job reuse, positive/zero exhausted budgets and every
optional-provider fallback. Real durable attempts verify owner-only reads/submissions,
server-bounded timing, local normalization and idempotent confirmation.
Normal mocked calls allow SDK cold startup; a separate case keeps a short provider timeout.
No API or database schema changes require regeneration.

Verification on 2026-11-14: `dev.ps1 check` passed; the final combined scenario/framework/
LLM/job selection passed **106 tests** (48 scenario cases). Final backend Ruff formatting,
lint and basedpyright passed. Initial missing pytest was resolved by `uv sync --frozen`.
Five-second normal mock timeouts proved too short under concurrent worktree load and were
raised to 30 seconds; the explicit short-timeout case remains. The durable-attempt fixture
was corrected to create auth preferences in the same database as its card.
An optional full backend run was deliberately stopped under concurrent worktree load, not
reported as passing; the focused combined run passed afterward. No task-prefixed test database
remained after the completed runs/cancellation. Pylance signature inspection timed out; actual
runtime tests and basedpyright validated the backward-compatible optional job keyword.
No live DeepSeek, frontend test sweep, E2E or stack lifecycle operation was performed.

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

## Per-user FSRS optimization (7.1.5)

From `backend`, run:

```powershell
uv run --no-sync pytest -q tests\unit\test_fsrs_optimization_unit.py tests\integration\test_fsrs_optimization_integration.py tests\integration\test_fsrs_optimization_resilience.py tests\integration\test_fsrs_optimization_migration.py tests\api\test_fsrs_optimization_api.py tests\integration\test_srs_reviews.py tests\integration\test_schema_snapshot.py
```

The real optimizer probe uses 512 qualifying transitions and checks that the installed
py-fsrs optimizer changes its defaults, or explicitly reports `unavailable` when its optional
extra is absent. Other deterministic tests use injected outputs and isolated owner histories:
511/512 boundaries, same-day transitions, incomplete/foreign/corrupt/outlier records,
bounded recent-window selection, repeat/cooldown/new-history behavior, concurrent/stale claims,
invalid outputs, unavailable/failure preservation, default fallback and future-only reviews.
They check unchanged cards, receipts, history and nondefault user preferences, plus the actual
authenticated API → job → worker path. No LLM, audio or image provider is contacted.

Fresh and pre-0024 upgrade databases verify replay, owner identity, data preservation and
indexes on the existing isolated 8101 harness. Regenerate only the snapshot when needed with
`uv run --no-sync pytest -q tests\integration\test_schema_snapshot.py --update-snapshot`,
then rerun without the flag. `pwsh -NoProfile -File scripts\tests\release.Tests.ps1` verifies
that the optimizer release flag affects only the API image build. No shared service lifecycle
operation is necessary.

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

### Portability E2E (6.1.6)

`frontend/e2e/portability.spec.ts` signs in as the administrator, creates a uniquely named
project with the fixture word `cat` through the API, exports it from the project page (checking
the saved file name and that the archive carries neither the password nor the access token),
then imports the archive twice from `/projects` with **Import progress** and **Start fresh**.
It asserts the `include_progress` query, the server summary and the localized success text,
opens each imported project, and checks that page text and `src`/`href` attributes contain no
local paths, `/api/media` URLs, external URLs or credentials. `finally` deletes the original and
both imported projects. Use the same fixture-backed stack as the project-to-word E2E, then run
`pnpm --dir frontend exec playwright test portability.spec.ts` (or `dev.ps1 test -E2E`).

### Review-session E2E (3.3.4)

`frontend/e2e/review-session.spec.ts` uses a unique learner and project, completes the forced
password change, and adds fixture nouns `schedule`, `bank`, `decision` and `cat`. These have
POS noun and Zipf band 4, providing safe offline distractors. Explicit sense priority puts
`schedule` first; its fixture definition is “A plan listing times for activities.” New cards
use recognition: the test answers either public `def2word` or `word2def` with fixture knowledge,
not a private answer specification. No provider, database inspection or mocked transport is used.

The flow opens **Study plan** and **Start review** through the UI, checks server feedback and
the selected suggested rating, overrides it, and confirms. A daily-new limit of one makes the
updated queue empty while three unintroduced senses remain. It checks the completed count,
reloads, reads the same public attempt and receipt, repeats the identical confirmation through
the generated-type API client, and verifies the unchanged receipt/count/queue and reloaded UI.
The existing integration test
`test_srs_reviews.py::test_identical_retry_concurrency_stale_conflict_and_durable_receipt`
already verifies concurrent/retried completion produces one review-log row, including a manual
rating override; no duplicate backend test is needed.

Use the ready fixture-backed stack on **main** (8100/8000/5173). Set `LEXICON_PATH` to the
absolute `backend\tests\fixtures\lexicon_small.sqlite` path, `LLM_DAILY_BUDGET=0`,
`AUDIO_NETWORK_ENABLED=false`, and a placeholder `DEEPSEEK_API_KEY` in main's gitignored
`.env.dev` before starting the API/worker. Keep administrator credentials only there as well;
`dev.ps1` loads them. The test checks the two offline environment flags, but the runner's
environment is not proof of the already-running API/worker configuration. Do not download
providers/models/audio or start/stop the stack from a task worktree.

After merging, run `.\scripts\dev.ps1 test -E2E` on main. For just this flow, with the same
environment already loaded, use `pnpm --dir frontend exec playwright test review-session.spec.ts`.
`pnpm --dir frontend exec playwright test review-session.spec.ts --list` is discovery only.
Tracing, video, screenshots and automatic error snapshots remain disabled by the existing
Playwright configuration; credential entry uses the evaluation helper, not logged fill arguments.
Nested `finally` blocks delete only the captured project and disable only the captured learner
even if project deletion fails. Disabled learner/history retention is intentional; no user-delete
endpoint or development-database reset is involved.

Worktree validation: `dev.ps1 check`, `dev.ps1 test -Frontend`, explicit E2E TypeScript checking
and Playwright discovery passed. Initial checks required restoring missing worktree-local
dependencies; no main environment links were created. The main-worktree
`dev.ps1 test -E2E` run passed all three browser flows with providers disabled.
The first review run reached the correct persisted overridden receipt but failed a redundant
Chromium request-body inspection (`postDataJSON()` was unavailable for the fetch request).
The test verifies the authoritative persisted rating, receipt and retry/count invariants
instead; the subsequent complete browser run passed without retries.

The first-login flow selects English via the existing browser preference format, signs in as
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

## Bundle contract tests (6.1.1)

Pure unit tests (no database): `tests/bundle_support.py` holds repository-shaped rows for all
seven dictionary tables, all nine edges (shared and owned), a project with hidden/ordered
memberships, an override, a note, owned image + shared audio media, memory, review logs and
preferences. From `backend`:

```powershell
uv run --no-sync pytest -q --basetemp=.pytest_bundle tests\unit\test_bundle_contract.py tests\unit\test_bundle_archive.py
```

They cover: schema file drift, full round trip (rows → `data.json` → validated entries → row
fields/IDs), byte-stable repeated serialization and archives, absence of private IDs and
credentials, foreign-owner rejection, invalid data (missing fields, wrong types, newer
revisions, dangling refs, owner/edge combinations, unsafe media metadata), unsupported
versions failing before extraction, unsafe archive members (traversal, absolute, backslash,
symlink, device, duplicates, extras), integrity mismatches, size/count limits and
no-partial-archive cleanup. Regenerate the schema after model changes with
`uv run python -m app.domain.bundle`.

## Project export tests (6.1.2)

Real-database API tests (`tests/api/test_project_export.py`, seed helpers in
`tests/api/project_export_support.py`) run on an isolated per-test database on 8101 with private
media and `bundle_work_dir` directories under the backend folder (`.project-export-*`, removed
after each test). They download `GET /api/projects/{id}/export` and open the archive with
`load_bundle`, checking: project tree (lemma → lexeme → selected senses only), membership
hidden/`study_order`, overrides, notes (target + project), owned tag edge, memory and review log,
content-addressed media bytes, attribution, and absence of storage paths and source IDs. A
second account (project, override, note, owned tag/sentence edges, media, progress on the same
shared senses) and the user's other project must not appear; foreign export is 404 and anonymous
401. Also covered: empty project, shared-only project, missing/directory/unsafe media and a
missing pronunciation audio file (skipped and counted in `X-PandaWords-Skipped-Media`), and an
archive-writer failure leaving no work directory. From `backend`:

```powershell
uv run --no-sync pytest -q tests\api\test_project_export.py
```

## Project import tests (6.1.3)

Real-database API tests on an isolated per-test 8101 database with private media/work dirs
(`.project-import-*`): `tests/api/test_project_import.py` (round trips) and
`tests/api/test_project_import_failures.py`, helpers in `tests/api/project_import_support.py`
(`seed` builds and exports a project; `rebuild` re-packs an export after editing its JSON;
`snapshot` counts shared rows and each user's owned rows). Covered: shared rows merged without
overwrite, owned ID/reference remapping (tag + `member_of`, notes, media file copy), hidden and
ordered memberships, own-lemma reuse, repeated imports (new copy each time), same-source
default progress on vs. another user's default off, explicit on (card + log, `project: null`
fallback, rebuilt receipt) and off (new card, no logs), existing memory/override kept and no
duplicate attempts, cross-user isolation (bob's copies are his own; alice cannot read them),
lemma-identity and forged shared-ref (`shared_identity`) conflicts, malformed/traversal/empty/
oversized uploads, oversized and non-decodable media, and database or file-copy failures
(rollback, copied files removed). Each failure asserts unchanged row counts, unchanged media
files and an empty work directory. From `backend`:

```powershell
uv run --no-sync pytest -q tests\api\test_project_import.py tests\api\test_project_import_failures.py
```

## User backup and restore tests (6.1.4)

Real-database API tests on the isolated 8101 harness, helpers in
`tests/api/user_backup_support.py` (`seed_user` = the project-import seed plus a second project
and customized preferences; `wipe` deletes all of a user's rows; `rebuild_user` re-packs an
edited backup). `tests/api/test_user_backup.py`: archive content (no account fields or IDs, all
projects/memberships/notes/overrides/media/memory/logs/preferences); wipe → restore equals the
original snapshot with preferences restored and account unchanged; repeated restore is a no-op
(`already_restored`, no new rows/receipts); after deleting the projects a restore runs again
without duplicating memory/history or overwriting customized preferences; restore into another
user (lemma-identity 409 without writes, then a rebuilt bundle) remaps ownership while the
source user's rows, preferences, account and media stay unchanged and inaccessible.
`tests/api/test_user_restore_failures.py`: anonymous 401, wrong format, garbage, invalid media
and oversized uploads fail before mutation with an empty work dir; an interrupted restore
(receipt write failure) rolls back everything incl. copied media; concurrent duplicate restores
apply once; empty-user round trip; an interrupted backup download leaves no staging files.
From `backend`:

```powershell
uv run --no-sync pytest -q tests\api\test_user_backup.py tests\api\test_user_restore_failures.py
```

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
