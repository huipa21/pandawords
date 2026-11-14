# Progress log

The main agent's working journal, edited on `main` only. Status per task lives in [PLAN.md](PLAN.md).
This file holds what the status column can't: the current run, blockers with reasons, discovered
backlog, and findings. Read it first when resuming ([../dev/workflow.md](../dev/workflow.md#resume-after-an-interruption)).

Durable knowledge goes to its topic doc (SurrealQL → [../dev/surrealdb-notes.md](../dev/surrealdb-notes.md),
design → ADR in [../decisions/](../decisions/)); the log entry just links to it.

## Current run

Request: implement all Phase 2 tasks with dependency-driven parallel agents (maximum five).
Phase 1 dependencies are all ✅. Schedule ready tasks immediately after their prerequisites
are merged and verified, without waiting for unrelated tasks in the same wave.
Pre-existing Phase 2 plan/details are included unchanged except task statuses.
Pre-existing browser output is preserved pending final artifact review; no secrets or transient
browser logs will be committed as source.

| Task | Branch | Worktree | State / notes |
|---|---|---|---|
| 2.1.2 | task/2.1.2-core-lexicon | ../pandawords.worktrees/2.1.2 | Starting; streaming SQLite builder |
| 2.3.1 | task/2.3.1-project-schema | ../pandawords.worktrees/2.3.1 | Starting; project and overlays |
| 2.5.1 | task/2.5.1-media | ../pandawords.worktrees/2.5.1 | Starting; authenticated media |
| 2.6.1 | task/2.6.1-word-components | ../pandawords.worktrees/2.6.1 | Starting; shared word UI |

## Blocked

| Task | Blocked by (task, tool, decision) | Since | Notes |
|---|---|---|---|

## Backlog (discovered, not yet in PLAN.md)

| Found in | Item | Proposed home (task ID / new task) |
|---|---|---|

## Log

Newest first. One entry per finished, blocked, or interrupted task. Every entry records completed
work, dependencies, verification outcomes, skipped work and reasons, failures and known causes,
and follow-ups. Use "none" or "not applicable" explicitly; do not record secrets.

<!-- ### YYYY-MM-DD — X.Y.Z Title
- Result / completed: merged / blocked / partial; work done; branch / commit
- Dependencies: checked task IDs and status, or none
- Verification: commands and actual outcomes (passed / failed / not run)
- Skipped / deferred: work and reason, or none
- Failures / causes / corrections: known cause or unknown; corrective action, or none
- Findings: …
- Blockers / follow-ups: next action, newly ready tasks; link Backlog / Blocked as needed -->

### 2026-11-14 — 2.2.1 Shared dictionary schema
- Result / completed: seven SCHEMAFULL dictionary tables and nine enforced relations, nested
  field types, ownership and indexes; `d757d55` merged with generated schema snapshot.
- Dependencies: 1.3.4 and 1.3.5 checked ✅. Project schema and media now ready and starting.
- Verification: real SurrealDB 3.3.5; agent 47 focused tests, snapshot-update and normal backend
  each 238 passed, `check` passed. Main merge `check` and combined backend/frontend passed
  (321 backend tests).
- Skipped / deferred: media metadata to 2.5.1; project overlays to 2.3.1, as planned.
- Failures / causes / corrections: initial missing environments restored after failed commands;
  syntax findings verified and documented. No unresolved failures or blockers.
- Follow-ups: branch/worktree removed after verification; repeat migration and drift covered.

### 2026-11-14 — 2.1.1 Lexicon downloads
- Result / completed: independent official-first downloads, explicit fallbacks, pinned checksums,
  manifest and atomic staging; `046525d` merged. Documentation and mocked failure tests included.
- Dependencies: 1.2.1 checked ✅; 2.1.2 now ready and starting immediately.
- Verification: agent `check`, 22 focused tests and backend 213 passed; main merge `check`
  and combined `test -Backend -Frontend` passed (274 backend tests).
- Skipped / deferred: full multi-gigabyte downloads not needed for mocked acceptance;
  builder belongs to 2.1.2. No unresolved failures or blockers.
- Findings: Kaikki upstream endpoint deprecation documented. Identifier task cleanup initially
  left a Windows directory; exact remaining directory was removed and absence verified.
- Follow-ups: source manifest interface available to builder/packaging. Download worktree and
  branch removed after verification; no unrelated files removed.

### 2026-11-14 — 2.2.2 Dictionary identity helpers
- Result / completed: deterministic normalized dictionary keys and strict URL-safe structured
  record-ID conversion; `1614668` merged to main. Existing jobs unchanged.
- Dependencies: 1.2.3 checked ✅.
- Verification: agent `check` passed; 61 new tests and isolated readiness rerun passed after
  two timing failures in the concurrent full run. Main merge `check` and combined
  `test -Backend -Frontend` passed (252 backend tests).
- Skipped / deferred: UUID/range/tuple record keys unsupported and explicitly documented;
  no requested dictionary ID shape deferred. No unresolved failures or blockers.
- Findings / follow-ups: dictionary repository and API tasks can reuse the new helpers;
  remaining prerequisites still pending. Task branch/worktree removed after verification.

### 2026-11-14 — Phase 2 preparation and baseline
- Result / completed: included the existing Phase 2 details and plan link in `b88db12`;
  started four independent root tasks in isolated worktrees, maximum five concurrent agents.
  Preserved pre-existing browser snapshots locally and ignored transient tool output in `c3fe592`.
- Dependencies: all Phase 1 prerequisites checked ✅; no Phase 2 dependency bypassed.
- Verification: main `check` passed; backend baseline 191 passed. Frontend baseline 64 passed
  and one token-enforcement test timed out at 20s during parallel environment setup; targeted
  rerun `pnpm exec vitest run src/design/enforcement.test.ts --reporter=dot` passed all 12.
- Skipped / deferred: E2E and integrated Phase 2 acceptance pending implementation.
- Failures / causes / corrections: initial progress patch partially applied because the table
  separator differed; retried only the remaining file successfully. Baseline timeout was
  transient concurrent CPU contention; no test timeout or product behavior changed.
- Blockers / follow-ups: none currently; integrate finished prerequisites and dispatch dependents.

### 2026-11-14 — 1.6.6 First-login E2E and Phase 1 completion
- Result / completed: planned Playwright dependency/config and one Chromium UI flow, generated
  contract types, isolated learner cleanup, safe credential inputs and disabled recordings;
  `9fab165` merged, exact real-run corrections committed as `eddaa42`.
- Dependencies:1.5.6/1.6.1 are ✅; all29 Phase1 tasks are now ✅.
- Verification: actual main `up`, `test -E2E`, then final `check` and combined
  `test -Backend -Frontend -E2E` passed:191 backend tests,65 frontend tests and1 Chromium E2E.
  Final frontend production build passed. Full flow: admin UI creates unique learner, temporary
  password login forces change, in-app Projects attempt stays gated, password change reaches
  Projects; cleanup disables only that learner. Zero skipped tests or success-shaped fallbacks.
  Final down exited all21 owned host/child processes; dev ports8000/5173/8100 closed.
- Skipped / deferred: live remote/Docker deployment not run; later phases intentionally untouched.
- Failures / causes / corrections: initial real E2E timed out on required-label asterisk; fixed
  prefix locators. Replaced full reload with in-app brand-link navigation because refresh
  intentionally denies pending-change users. Reran required command and combined suite successfully.
  Existing Starlette/httpx deprecation warning remains; no unresolved code/test failure.
- Findings: Chromium download/launch and package install verified with TLS enabled. API/schema
  snapshots and frontend contracts remain committed. Release/image/production acceptance recorded
  below. Generated E2E learners remain disabled in dev DB because no delete API exists.
- Blockers / follow-ups: none for Phase1. All task branches/worktrees removed, leaving main only;
  pre-existing Phase2 heading/details and browser-output folder preserved, no push requested.

### 2026-11-14 — Integrated release acceptance
- Result / completed: main `dev.ps1 release -Version0.1.6913` built current API/worker and
  responsive admin frontend into versioned image/deploy archives and SHA256SUMS.
- Dependencies: all runtime tasks are ✅; E2E tooling1.6.6 remains in progress.
- Verification: both hashes, exactly four deployment members, two image configs/platforms
  linux/amd64, and clean initially-empty tmpfs/VFS-store load/identity/count checks passed.
  Disposable store unmounted/removed; shared image store unchanged by the load check.
- Skipped / deferred: live Docker/remote server deployment not run; E2E runner verification pending.
- Failures / causes / corrections: first final image inspect failed because PowerShell pipeline
  appended CR to its last argument; isolated store trap cleaned it. Repeated complete clean-store
  load with final shell-comment terminator passed. Documented Windows pipeline pitfall.
- Findings: archive images include all Phase1 runtime features; release command fails closed
  on existing artifacts rather than silently overwriting.
- Blockers / follow-ups: none.

### 2026-11-14 — 1.6.1 Complete development commands
- Result / completed: up/down/check/test selectors, dev-only seeds entrypoint, locked/PID-safe
  lifecycle with native Windows Job Objects/process hosts, ready checks, logs and rollback;
  `82bcf41` merged. Existing setup/DB/gen-api/release behaviors preserved.
- Dependencies:1.3.3/1.4.3/1.6.2 are ✅.
- Verification: main `check` and combined `test -Backend -Frontend` passed (191 backend tests;
  frontend65 already verified and selector passed). Real main `up` twice returned API readiness200
  and login200; browser at printed localhost URL showed functioning Chinese login form. `down`
  twice exited all21 recorded owned host/child processes; ports8000/5173/8100 closed. Actual
  lint-error fixture detected RuffF821/nonzero, removed itself, then main check passed.
  Agent process-tree/PID-reuse/rollback/selector and existing release/backend/hook guards passed.
- Skipped / deferred: E2E selector intentionally requires forthcoming1.6.6 config.
- Failures / causes / corrections: initial parent harness inherited expected native lint-failure
  exit code from same-shell fixture; child-shell execution proved fixture passes and restored check
  passes. No production-code failure. Earlier manually started Vite children needed explicit
  PID cleanup; new lifecycle owns full native jobs and real down proved no survivors.
- Findings: no source change or secret/environment override was needed for default main up;
  dev data retained and no unrelated process was stopped.
- Blockers / follow-ups: none;1.6.6 now ready.

### 2026-11-14 — 1.5.6 Responsive admin users UI
- Result / completed: desktop table/mobile cards, pagination/load/empty/error states, create/reset
  temporary-password dialogs and copy feedback, confirm actions, self protection, bilingual errors,
  required shared app components and preview entries; `efc0244` merged.
- Dependencies:1.5.4/1.5.5 are ✅.
- Verification: main lint/typecheck,65 default frontend tests, build and backend checks passed.
  Real API browser1280px: create, display/copy password, disable/enable, promote/demote, confirmed
  reset and self-action protection passed. At375px: cards instead of table, create/toggle/confirmation,
  password dialog, no horizontal/modal overflow, and action targets≥44px passed.
- Skipped / deferred: E2E runner still1.6.6; no unrelated shared catalogue components implemented.
- Failures / causes / corrections: browser harness initially expected input instead of output
  for password and confirmation for non-destructive enable; corrected harness, actual actions passed.
- Findings: responsive action wrapping preserves target size and desktop navigation.
- Blockers / follow-ups: none; waiting on1.6.1 for wave12.

### 2026-11-14 — Integrated worker/image/production acceptance
- Result / completed: API/worker and full admin frontend linux/amd64 images built; image worker
  processed noop exactly once as UID10001 and gracefully stopped, disposable database removed.
- Dependencies: completed1.6.2/1.5.4/1.5.5/1.5.6 and existing1.6.3/1.6.4.
- Verification: isolated production compose `config --quiet`/`up --pull never`, successful migration,
  worker/API UID10001 and Caddy-network proxy200 readiness passed. All smoke project containers,
  volumes and networks removed, without changing shared dev/test data.
- Skipped / deferred: live Docker/server deployment not run; final archive build still pending.
- Failures / causes / corrections: exact Compose validation exposed worker accidentally nested in
  API depends_on; moved it to top-level services (`3401f88`), reran validation and real production
  startup successfully. No silent acceptance claim from backend tests alone.
- Findings: backend runtime needs no dev dependencies; full service dependency ordering works.
- Blockers / follow-ups: none. Wave10 task branches/worktrees are removed; UI/API helpers closed.

### 2026-11-14 — 1.5.4 Admin users API
- Result / completed: paginated credential-free list, create/reset temporary passwords, role and
  disable controls, atomic session revocation, self/last-enabled-admin guards; `83b367b` merged
  as `1d1daad` with combined0003/0004 snapshot and regenerated API contracts.
- Dependencies:1.5.3 is ✅.
- Verification:18 focused cases and branch176 backend tests passed; combined main189 tests,
  Ruff/format/basedpyright and frontend lint/types/43 tests passed; normal snapshot check left
  generated snapshot unchanged. Real independent transaction races prove last-admin protection.
- Skipped / deferred: admin UI remains1.5.6; no admin learning-data access added.
- Failures / causes / corrections: expected router/generated snapshot/contracts conflicts
  integrated without dropping jobs; generator rewrote contracts. Initial concurrent test
  contention passed isolated reruns; no timeout changes. Existing Starlette warning remains.
- Findings:0004_admin_guard serializes mutations and prevents write-skew; migration gaps work.
- Blockers / follow-ups: none.

### 2026-11-14 — 1.5.5 Frontend auth
- Result / completed: NForm login/password pages, memory-only Pinia tokens, shared session restore,
  user/admin/forced-change guards, logout and bilingual errors; `d896538` plus expired-logout
  regression fix `7e3bd57` merged as `c8d2916`.
- Dependencies:1.5.3/1.4.3/1.4.5 are ✅.
- Verification: main default frontend suite59 tests, lint/typecheck/build passed; backend checks
  unchanged clean. Real browser against isolated SurrealDB-backed API passed admin login,
  httpOnly/Strict/path cookie, reload restore, memory-only token, actual signed-expired-token
  logout401→refresh200→logout204 and cookie removal/reload logged-out; created user forced-change
  redirect, hidden admin links, password change and post-change restore passed.
- Skipped / deferred: responsive admin actions remain1.5.6; E2E runner remains1.6.6.
- Failures / causes / corrections: expired logout initially left cookie, fixed with independent
  refresh/revocation and focused failing-before/passing-after regression. Agent parallel test
  resource contention resolved; normal main tests passed without timeout changes.
- Findings: auth state never persisted; explicit cookie mutations serialize logout/relogin.
- Blockers / follow-ups: none. Bounded Vite/API helpers stopped; isolated test DB cleaned up.

### 2026-11-14 — 1.6.2 Worker and jobs
- Result / completed:0003_job, owner-scoped jobs endpoint, conditional atomic claims, noop registry,
  LIVE wakeup/reconnect with5s polling fallback, bounded exponential retries and graceful shutdown;
  worker compose service and generated contracts; `953e6a2` merged before admin integration.
- Dependencies:1.3.4/1.3.5/1.5.3/1.6.4 are ✅.
- Verification: branch full170 tests plus final focused15 passed; integrated main171, then
  combined admin189 backend tests passed; Ruff/format/basedpyright and frontend checks/tests
  passed. Snapshot explicit-update followed by normal comparison passed. Real3.3.5 independent
  WS exactly-once claim, LIVE CREATE/UPDATE, disconnect/reconnect, retries and shutdown tested.
- Skipped / deferred: integrated production image/compose smoke scheduled for final acceptance;
  abrupt-crash running jobs require documented manual recovery, beyond graceful-shutdown skeleton.
- Failures / causes / corrections: Windows signal registration regression fixed/tested;
  known Starlette warning remains; no unresolved implementation failures.
- Findings: verified SQL/LIVE behavior recorded in SurrealDB notes.
- Blockers / follow-ups: none;1.6.1 now ready.

### 2026-11-14 — 1.5.3 Auth API
- Result / completed: five auth endpoints, strict cookie, reload-based current_user/require_admin,
  forced-change gate, bounded username/IP exponential login backoff; atomic password change
  revokes old sessions and issues usable tokens; `fca8fe3` merged as `066f873`.
- Dependencies:1.5.2 is ✅.
- Verification: integrated Ruff/format/basedpyright, backend158 tests, frontend lint/typecheck
  and43 tests passed;26 focused API cases cover generic login failures, cookie flags, rotation,
  logout, gate, disabled user, owner isolation and stale-login/password-change races. Generated
  frontend API contracts from OpenAPI; hooks passed.
- Skipped / deferred: aggregate scripts remain1.6.1; actual browser auth awaits1.5.5.
- Failures / causes / corrections: missing worktree dependencies restored locked/offline;
  duplicate test module name fixed. Existing Starlette warning remains; Pylance worktree unavailable
  but standalone typecheck/runtime tests passed.
- Findings: forced-change refresh is403 and clears cookie; public login grants the token needed
  for me/password/logout, and password change returns fresh usable access/refresh credentials.
- Blockers / follow-ups: none; wave10 tasks now ready. Wave8 branch/worktree removed.

### 2026-11-14 — 1.5.2 Security core
- Result / completed: recovered and assembled unfinished work with parallel implementation and
  test agents; Argon2id, validated HS256 JWT, opaque refresh hashing, atomic rotation/reuse-chain
  revocation, logout, exactly-once admin bootstrap and readiness initialization; `a21d81f` merged.
- Dependencies: 1.5.1 is ✅.
- Verification: integrated Ruff/format/basedpyright clean; backend132 tests and frontend43 tests,
  lint/typecheck passed. Independent WebSocket refresh/bootstrap race, cancellation, isolation,
  expired/tampered claims and startup failure cases passed. Hooks passed.
- Skipped / deferred: aggregate script remains1.6.1; public auth endpoints remain1.5.3.
- Failures / causes / corrections: stopped shared Podman machine restarted and test8101 verified;
  conflict retry/cancellation cleanup fixed with focused regressions; missing worktree hook deps
  restored from locked offline cache. Existing Starlette warning remains. Pylance worktree
  unavailable; standalone typecheck and runtime tests passed.
- Findings: reuse revokes its family, not independent sessions or other owners; rollback failures
  logged safely; health remains200 while readiness awaits bootstrap.
- Blockers / follow-ups: none;1.5.3 now ready. Corrected previously omitted1.6.5 completion status
  using its already committed verification log; unrelated Phase2 edits preserved.

### 2026-11-14 — 1.5.1 Auth schema
- Result / completed: immutable0002_auth user/refresh-token schema, indexes and regenerated
  snapshot; `551984d` merged as `4d71e4b`. Branch/worktree removed;0001 unchanged.
- Dependencies: 1.3.4 and1.3.5 are ✅.
- Verification: real3.3.5 duplicate username rejection, snapshot-update and normal suites passed;
  integrated backend Ruff/format/basedpyright and91 tests, frontend lint/typecheck and43 tests
  passed. Hooks passed.
- Skipped / deferred: make_user awaits1.5.2; aggregate check awaits1.6.1.
- Failures / causes / corrections: missing pytest resolved via locked offline sync; Pylance timed
  out but direct typecheck passed. Existing Starlette warning remains.
- Findings: required prefs and role/theme/accent unions are enforced by schema.
- Blockers / follow-ups: none.

### 2026-11-14 — 1.6.5 Release bundles
- Result / completed: versioned linux/amd64 image archive, deploy bundle and SHA256SUMS tooling;
  `f98dd6b` merged as `dffc8db`. Branch/worktree removed.
- Dependencies: 1.6.4 is ✅.
- Verification: focused PowerShell guard/manifest/hash tests passed on branch/main; actual release
 0.1.165 built both images, loaded matching IDs into initially empty isolated tmpfs/VFS store within
  180s and removed store without touching shared images. Deploy manifest contains compose.yml,
  .env.example, Caddyfile.snippet, VERSION. Commands recorded in deployment.md.
  Main backend checks/91 tests and frontend checks/43 tests passed.
- Skipped / deferred: Docker daemon/production deployment not tested; restore.sh belongs to6.1.5.
- Failures / causes / corrections: none.
- Findings: exact multi-image save/load flags and clean-store procedure verified.
- Blockers / follow-ups: none.

### 2026-11-14 — 1.3.4 Schema snapshots
- Result / completed: canonical schema JSON, readable drift test and explicit update plugin;
  `80d71fb` merged as `c6b63c8`; branch/worktree removed.
- Dependencies: 1.3.3 is ✅.
- Verification: real deliberate migration drift failed with table/field/index diff; explicit update
  restored passing comparison. Main standalone plugin run passed 69 tests; after harness merge,
  `dev.ps1 test -Backend -UpdateSnapshot` passed 78 tests and left committed snapshot unchanged.
- Skipped / deferred: aggregate check awaits 1.6.1.
- Failures / causes / corrections: registered plugin in integrated conftest; stdin Ruff needed
  explicit app/tests first-party classification. Pylance timed out; basedpyright passed.
- Findings: schema includes DB and every table's definitions, not records/runtime timestamps.
- Blockers / follow-ups: none.

### 2026-11-14 — 1.3.5 Isolated test harness
- Result / completed: session/fresh databases, lifespan-managed ASGI client and backend runner;
  `4ec156c` merged as `707e931`; branch/worktree removed.
- Dependencies: 1.3.3 is ✅.
- Verification: agent ran two concurrent pytest processes (76 passed each), observed overlapping
  distinct databases and verified exact cleanup. Integrated backend runner/update flag passed
  78 tests; command safety/startup/selector/snapshot forwarding tests passed.
- Skipped / deferred: make_user intentionally unfinished until 1.5.x; container-down runner path
  was mocked rather than stopping shared server. Aggregate check awaits 1.6.1.
- Failures / causes / corrections: testing-doc conflict retained empty fresh-db semantics and
  full snapshot details. Pylance timeout; direct typecheck passed.
- Findings: none.
- Blockers / follow-ups: implement make_user during auth work.

### 2026-11-14 — 1.6.4 Production compose and backups
- Result / completed: production services/networks/limits, fail-closed pre-migration backup and
  Caddy snippet/env/docs; `ad35149` merged as `3606eea`, settings fix `dfedc70`.
  Branch/worktree removed.
- Dependencies: 1.6.3, 1.3.3 and 1.3.2 are ✅.
- Verification: isolated production compose migrate exited 0, services healthy, web readiness200;
  fresh/existing exports restored exactly and unwritable backup failed nonzero. Owned synthetic
  containers/networks/volumes/files removed. Main Ruff/format/basedpyright, backend runner85 tests,
  frontend lint/typecheck and43 tests passed.
- Skipped / deferred: real server deployment not requested; full check awaits1.6.1.
- Failures / causes / corrections: upstream SurrealDB cannot write fresh portable named volumes
  as its default nonroot user; capability-free/no-new-privileges root for DB documented. API
  stays UID10001. Full integration caught missing APP_VERSION Settings field; added and retested.
  Existing Starlette warning and Pylance timeout remain; direct typecheck passed.
- Findings: verified HTTP exports prevent migration on backup failure.
- Blockers / follow-ups: none; wave7 ready.

### 2026-11-14 — 1.3.3 Transactional migration runner
- Result / completed: checksum-protected forward-only SQL/Python migration CLI and bootstrap;
  `daee119` merged as `4abf1fb`; branch/worktree removed.
- Dependencies: 1.2.3 and 1.3.2 are ✅.
- Verification: real isolated DB tests passed fresh application, no-op repeat, checksum rejection,
  SQL/Python rollback, dry-run and CLI exit codes; exact DB cleanup confirmed. Main Ruff/format/
  basedpyright and 67 backend tests, frontend lint/typecheck and 41 tests passed.
- Skipped / deferred: aggregate scripts remain unavailable until 1.6.1.
- Failures / causes / corrections: Pylance timed out; direct basedpyright passed. Existing
  Starlette warning remains. No other failures.
- Findings: verified UUID transactions make migration SQL/Python changes and tracking atomic.
- Blockers / follow-ups: none; 1.3.4/1.3.5/1.6.4 are ready.

### 2026-11-14 — 1.4.4 Dev-only design preview
- Result / completed: bilingual token/component preview and catalogue update; `2c60243` merged
  as `cb4abc8`; branch/worktree removed.
- Dependencies: 1.4.3 is ✅.
- Verification: agent browser checks passed 375px/1280px, both themes, translations, input/message
  interactions and no overflow; exact server PID stopped. Main production build and text/chunk
  scan confirmed no dev preview output. Frontend lint/typecheck and 43 Vitest tests, backend
  Ruff/basedpyright and 67 tests passed. Hooks passed.
- Skipped / deferred: aggregate scripts await 1.6.1.
- Failures / causes / corrections: cached deps restored with no downloads; favicon 404 remains
  unspecified by this task. Existing backend Starlette warning remains.
- Findings: none.
- Blockers / follow-ups: none.

### 2026-11-14 — 1.6.3 Container packaging
- Result / completed: multi-stage nonroot API and web Dockerfiles, context ignores and nginx
  configuration; `2aa6052` merged as `69f61d2`. Branch and worktree removed.
- Dependencies: 1.2.2 and 1.4.3 are ✅.
- Verification: both `podman build --platform linux/amd64` builds passed on the task branch and
  main; main images tagged `localhost/pandawords-api:phase1` and `localhost/pandawords-web:phase1`.
  Agent smoke tests passed API health 200, web index 200, SPA fallback, API proxy, readiness 503
  without DB, gzip, immutable caching, missing assets/internal media 404, nginx syntax and nonroot
  runtime checks. Exact smoke containers/network removed; images retained.
  Main Ruff/format/basedpyright and 57 backend tests, frontend lint/typecheck and 41 tests passed.
- Skipped / deferred: aggregate scripts await 1.6.1. Production compose belongs to 1.6.4.
- Failures / causes / corrections: none; official registries succeeded without TLS/config changes.
  Existing Starlette warning remains.
- Findings: none.
- Blockers / follow-ups: none for this task; 1.6.4 also needs 1.3.3.

### 2026-11-14 — 1.2.3 Database lifecycle
- Result / completed: process-local reconnecting SDK lifecycle and safe readiness service;
  commits `ed05b1f` and `6322f33` merged, final merge `46b3e5b`. Branch/worktree removed.
- Dependencies: 1.2.2 and 1.3.1 are ✅.
- Verification: real healthy readiness 200, unreachable readiness 503, healthz/startup unaffected,
  reconnect and offline OpenAPI passed. Follow-up localhost-configured readiness passed without
  private-env changes; integrated Ruff/format/basedpyright and 49 backend tests passed.
- Skipped / deferred: aggregate commands await 1.6.1. No unrelated work performed.
- Failures / causes / corrections: localhost resolves IPv6 first but compose publishes IPv4-only;
  explicit default IPv4 URLs and URL-parsed literal-localhost normalization resolve the reproduced
  timeout while preserving external hosts and explicit IPv6. Pylance tool timed out; direct
  basedpyright passed. Existing Starlette warning remains.
- Findings: SDK 3.0.0/server 3.3.5 confirmed; N02/N03 facts shared with spike agent.
- Blockers / follow-ups: none.

### 2026-11-14 — 1.3.2 SurrealDB verification spike
- Result / completed: regression script and DB-scoped probe helpers, all 23 syntax/API facts and
  working alternatives recorded; `1c6478a` merged as `6a95da2`. Branch/worktree removed.
- Dependencies: 1.3.1 and 1.2.1 are ✅.
- Verification: main spike passed 23/23 against 3.3.5/SDK 3.0.0, including rollback, exact cleanup,
  stable schema info and complete HTTP export/import. Main Ruff/format/basedpyright and 57 backend
  tests passed; frontend lint/typecheck and 41 Vitest tests passed. Generated DBs removed; shared
  test server remains healthy.
- Skipped / deferred: unverified CLI export not used; verified SDK HTTP backup is the alternative.
  Aggregate check/test remains unavailable until 1.6.1.
- Failures / causes / corrections: N17's no-argument transaction belief is false; verified UUID
  transaction argument forms replace it. Existing Starlette warning remains.
- Findings: 22 notes ✅, N17 ❌ with working replacement; all acceptance prerequisites resolved.
- Blockers / follow-ups: none; wave 5 is ready.

### 2026-11-14 — 1.4.3 App shell
- Result / completed: responsive app/auth layouts, navigation and providers, persisted theme and
  locale preferences, bilingual placeholder routes, Lucide/Naive imports; commit `984f8c7` merged
  as `300f265`. Task branch and worktree removed.
- Dependencies: 1.4.2 is ✅.
- Verification: agent browser checks passed at 375px/1280px without overflow, system-theme
  following, synchronized Naive/CSS colors, persisted preferences and auth layout. Main frontend
  build/lint/typecheck and 41 Vitest tests passed; backend Ruff/format/basedpyright and 22 pytest
  tests passed. Commit hooks passed. Agent stopped its smoke server by PID.
- Skipped / deferred: auth/admin guards belong to 1.5.5; aggregate check/test remains unavailable
  until 1.6.1.
- Failures / causes / corrections: package/lockfile merge conflicts retained both independent
  dependency additions; frozen offline installation passed. Unspecified favicon returns 404;
  no application errors. Existing backend test-client deprecation warning remains.
- Findings: none beyond the documented missing favicon.
- Blockers / follow-ups: none for this task; 1.4.4 and 1.6.3 are ready after wave 4 completes.

### 2026-11-14 — 1.4.5 API types pipeline and client
- Result / completed: deterministic offline OpenAPI/TypeScript generation, typed API client,
  shared refresh/retry/logout lifecycle and normalized errors; commit `7693724` merged as
  `99d9991`. Task branch and worktree removed.
- Dependencies: 1.4.1 and 1.2.2 are ✅.
- Verification: on main, gen-api reproduced committed files; frontend build/lint/typecheck and
  Vitest passed (35 tests, including 9 client cases); backend Ruff/format/basedpyright and pytest
  passed (22 tests). Active hooks passed on the task commit.
- Skipped / deferred: real auth integration awaits 1.5.3; mocked lifecycle tests cover concurrent
  401s and refresh failures. Aggregate check/test commands remain unavailable until 1.6.1.
- Failures / causes / corrections: none. Existing Starlette test-client deprecation warning remains.
- Findings: openapi-typescript's TypeScript peer range names 5.x; generation and checks pass on the
  required pinned TypeScript 6. No TypeScript downgrade or handwritten API types were introduced.
- Blockers / follow-ups: none for this task; regenerate contracts after future backend changes.

### 2026-11-14 — Wave 3 integration and recovery
- Result / completed: 1.1.3 hooks (`73a5fec`, `2e53492`, merge `87aae46`, integration fix `f0204ab`);
  1.3.1 databases (`ab2e561`, merge `eed2bd5`); 1.4.2 tokens (`f1900d9`, merge `767db47`);
  and the reopened 1.2.2 logging fix (`fa9b9d8`) are merged. All four branches and worktree folders
  were removed; only main remains.
- Dependencies: 1.1.3 checked 1.2.1/1.4.1; 1.3.1 checked 1.1.2; 1.4.2 checked 1.4.1;
  1.2.2 checked 1.2.1; all are ✅.
- Verification: backend Ruff, formatting, basedpyright and pytest passed (22 tests, including
  real Uvicorn and cancellation regressions); frontend build/typecheck/lint/Vitest passed
  (26 tests). Disposable database tests passed healthchecks, RocksDB persistence, memory reset,
  ownership refusal and dev reset without disturbing test data; all disposable resources removed.
  Hook suites passed 33 cases, including partial staging, synthetic env files and missing
  worktree-local dependencies; actual hooks installed on main.
- Skipped / deferred: aggregate check/test commands remain unavailable until 1.6.1; direct
  equivalents were used. Remote setup remains deferred without a supplied URL; no push performed.
- Failures / causes / corrections: lost agent contexts left committed/partial work; recovered
  it directly and reran validation. Real Uvicorn exposed raw exception re-logging; the narrowly
  scoped handled-response guard fixes it while cancellation/background/transport failures propagate.
  Hook fixtures needed token-rule files after merging; staged lint was extracted from eval into a
  script to fix worker preload resolution. pnpm 11 requires explicit lifecycle policy; automatic
  lefthook builds are disabled and its verified binary is installed explicitly.
  Windows worktree removal left clean tracked files; exact leftovers were removed and absence checked.
- Findings: pre-existing unrelated Phase 2 documentation edits appeared during integration and
  were preserved, not modified. The Node TLS override remains user-owned; network commands used
  certificate verification. One existing Starlette TestClient deprecation warning remains.
- Blockers / follow-ups: none for wave 3; proceed with 1.2.3, 1.3.2, 1.4.3 and 1.4.5.

### 2026-11-13 — 1.2.2 API skeleton
- Result / completed: added the app factory, settings, request logging, safe error responses,
  health/readiness stubs and offline OpenAPI generation. Task commits `9742b25`, `3f13bdb` and
  `ec30475` were merged as `c8d0dce`; the task branch and worktree were removed.
- Dependencies: 1.2.1 is ✅.
- Verification: on main, Ruff, formatting, basedpyright, pytest (17 passed), offline OpenAPI
  generation and frontend build, typecheck, lint and test (1 passed) all passed. The task agent
  also passed a bounded Uvicorn startup smoke test and stopped its process.
- Skipped / deferred: real database readiness belongs to 1.2.3. `dev.ps1 check` still returns
  `Unknown command 'check'`, and `dev.ps1 test` is not implemented until 1.6.1; available direct
  checks were run instead. E2E is not applicable yet.
- Failures / causes / corrections: initial review found the generic 500 handler did not log
  unexpected errors; a follow-up added a structured event with request ID and exception type
  without logging exception messages, and a focused test passed. Pytest reported one existing
  Starlette `TestClient`/httpx deprecation warning; tests passed.
- Findings: `auth.md` specifies a 60-minute access token while the existing settings/example
  default is 15 minutes; reconcile this when implementing 1.5.2 without modifying the private env.
- Blockers / follow-ups: none for this task. 1.4.5 is ready after wave 3; 1.2.3 also needs 1.3.1.

### 2026-11-13 — 1.4.1 Frontend project
- Result / completed: resumed the existing frontend scaffold, added bilingual hello-page text and
  completed its tooling. Task commits `2ecf4c6` and `e18850e` were merged as `c08586f`; the task
  branch and worktree were removed.
- Dependencies: 1.1.1 is ✅.
- Verification: on main, `pnpm install --frozen-lockfile --offline`, frontend `build`, `typecheck`,
  `lint` and `test` passed (1 test); backend Ruff, format check, basedpyright and pytest passed
  (1 test). The task agent also passed browser and `/api` proxy smoke checks. `git diff --check`
  passed.
- Skipped / deferred: `dev.ps1 check` returned `Unknown command 'check'`, and `dev.ps1 test` is not
  implemented until 1.6.1; equivalent available checks were run directly. No E2E test applies yet.
- Failures / causes / corrections: `git worktree remove --force` removed its Git registration but
  left generated `node_modules` and four clean tracked files on Windows; those specific leftovers
  were removed and the branch deletion and absent folder were confirmed. The browser requested an
  unspecified favicon and received 404; no icon asset is specified by this scaffold task.
- Findings: this environment sets `NODE_TLS_REJECT_UNAUTHORIZED=0`. The agent reported verifying
  its six added package hashes using certificate-checked HTTPS; the main install was offline with
  Node TLS verification enabled. Future network installs must explicitly enable verification.
- Blockers / follow-ups: none for this task. 1.1.3 and 1.4.2 are now ready; 1.4.5 still needs 1.2.2.

### 2026-11-13 — 1.1.3 lefthook pre-commit
- Result / completed: blocked before implementation; no code or configuration changes made.
- Dependencies: 1.2.1 is ✅; 1.4.1 is ⬜ in PLAN.md and its task branch is not merged.
- Verification: main worktree was clean; inspected PLAN.md and confirmed branch `task/1.4.1-frontend-project` has commit `2ecf4c6` but remains separate from main. Implementation checks were not run.
- Skipped / deferred: all 1.1.3 deliverables and acceptance checks, because prerequisite 1.4.1 is incomplete.
- Failures / causes / corrections: none.
- Findings: none.
- Blockers / follow-ups: complete and merge 1.4.1, then resume 1.1.3.

### 2026-11-13 — 1.1.2 `dev.ps1` skeleton
- Result / completed: Added command dispatch/help, main-worktree and `.env.dev` resolution,
  setup/tool checks, quiet command execution, fallback retries, and `.dev/logs` creation. Updated
  setup/worktree guidance. Task commits `ae1721c` and `9200c9c` were merged to `main` as
  `dae7ef3` and `61cd3bf`; status/progress close-out is committed separately.
- Dependencies: 1.1.1 is ✅.
- Verification: `./scripts/dev.ps1 help` and `./scripts/dev.ps1 setup` passed on PowerShell 7.7.
  Setup installed/confirmed Python 3.14.3 and, after backend 1.2.1 landed, `uv sync` passed.
  A linked-worktree smoke test confirmed that `TARGET_LANGUAGE` was loaded from the main
  `.env.dev` without printing its value. A forced official-command failure retried successfully
  with the fallback. `git diff --check` passed.
- Skipped / deferred: `pnpm install` was skipped because `frontend/` does not exist yet.
  `dev.ps1 check` and application tests were not run because the check command and test projects
  are not implemented yet. Compose-provider version probing was not part of setup because it
  requires a running Podman machine.
- Failures / causes / corrections: an initial `podman compose version` probe failed because the
  Podman machine was stopped; setup now checks Podman's installed version without requiring a
  running machine. The subsequent setup run exposed an empty fallback-source binding when backend
  `uv sync` was available; allowing the intentionally empty source fixed it, and setup passed.
- Blockers / follow-ups: none. Task 1.3.1 is now ready because its 1.1.2 dependency is ✅.

### 2026-11-13 — 1.2.1 Backend uv project
- Result / completed: Added the Python 3.14 backend project, dependency lock, lint/type-check/test
  configuration, and `app` package marker. Commit `bf2be71` was merged to `main` as `9004d94`.
- Dependencies: 1.1.1 is ✅.
- Verification: `uv sync --locked`, `uv run ruff check`, `uv run ruff format --check`,
  `uv run basedpyright`, `uv run pytest -q`, and `uv lock --check` passed on Python 3.14.3;
  pytest reported 1 passed. `git diff --cached --check` passed. The attempted
  `./scripts/dev.ps1 check` returned `Unknown command 'check'`; that command is planned for task
  1.6.1, so the backend checks were run directly.
- Skipped / deferred: no change to `conventions.md` was needed; its Python conventions already
  specify the selected Ruff and basedpyright rules. No other work was deferred.
- Failures / causes / corrections: initial pytest collection could not import `app` because the
  project directory was not on pytest's import path; adding `pythonpath = ["."]` fixed it and the
  complete check set then passed. `dev.ps1 check` remains unavailable until task 1.6.1.
- Blockers / follow-ups: none. This completes the 1.2.1 dependency for 1.2.2 and 2.1.1.

### 2026-11-13 — 1.1.4 VS Code workspace
- Result / completed: added `.vscode/settings.json` and `.vscode/extensions.json` in commit `d696e8f`, merged to `main` as `67114bd`; task worktree and branch were removed.
- Dependencies: 1.1.1 is ✅.
- Verification: PowerShell JSON parsing and targeted assertions verified all requested search/watcher excludes, the `backend/.venv` interpreter, ESLint flat config, UnoCSS root, and six extension recommendations. `git show --check d696e8f` passed. `./scripts/dev.ps1 check` was attempted but is not yet a supported command; `./scripts/dev.ps1 help` listed only `help` and `setup`. Application tests were not run because this task changes only VS Code configuration.
- Skipped / deferred: interactive VS Code search was not exercised; the configured excludes were validated directly. No application tests apply to these configuration-only changes.
- Failures / causes / corrections: `./scripts/dev.ps1 check` returned `Unknown command 'check'`; that command is planned for task 1.6.1, so it remains unavailable in the current repository.
- Blockers / follow-ups: none.

### 2026-11-13 — 1.1.1 Initialize repository (backfilled)

- Result / completed: local repository initialized on `main` in root commit `bd9afb1`.
  Added ignore, line-ending and editor settings, a safe [`.env.example`](../../.env.example),
  and a short [README](../../README.md); committed the existing docs and marked
  [PLAN.md](PLAN.md) complete. The original close-out omitted this log and the remote URL request.
- Dependencies: none. Existing `.git` and unborn `main` were reused; no reinitialization was needed.
- Verification: `git log -1` confirmed the initial commit on `main`; `git status --short --branch`
  confirmed a clean working tree. `git check-ignore -v .env.dev` matched; `.env.example` was not
  ignored and was tracked. Environment-key comparison matched all 30 keys without reading their
  values into the log. `git check-attr` confirmed LF text and binary image/audio/SQLite handling.
  `git diff --cached --check` passed; the staged-file check confirmed no private env files.
  For this documentation correction, `git diff --check` passed; application tests are not
  applicable to these documentation-only changes.
- Skipped / deferred: no task branch, worktree, or merge, per the explicit 1.1.1 exception.
  Application lint/build/tests were not run because application projects and `scripts/dev.ps1`
  do not exist yet. No GitHub remote was added because no URL was supplied; the required URL
  request was omitted rather than completed. No push was requested or performed.
- Failures / causes / corrections: no command failures were observed. I incorrectly treated the
  initialization exception as allowing close-out without a progress entry. This backfill corrects
  that omission, and [AGENTS.md](../../AGENTS.md) and [workflow.md](../dev/workflow.md) now explicitly
  require the complete progress record, including for 1.1.1. The initial commit also used
  `-c core.hooksPath=NUL`, unnecessarily bypassing hooks; this was not justified and is not
  evidence of passing hook checks. Follow-up commits must use the normal hook configuration.
- Blockers / follow-ups: no blocker to local development. Remote setup remains deferred until the
  user supplies a GitHub URL; the omitted URL request remains an unmet procedural acceptance item.
  Ready next: 1.1.2, 1.1.4, 1.2.1, and 1.4.1; none were started by this task.

### 2026-11-13 — 1.4.2 dependency check

- Result / completed: checked the task row and details for 1.4.2. It depends on 1.4.1, which
  remains ⬜ in [PLAN.md](PLAN.md); implementation was not started.
- Dependencies: 1.4.1 is not ✅, so the workflow's dependency gate blocks this task.
- Verification: `git status --short --branch` confirmed a clean `main` working tree before
  recording this blocker. No application checks were run because no code changed.
- Skipped / deferred: token implementation, generators, fonts, and enforcement are deferred until
  1.4.1 is complete and merged.
- Failures / causes / corrections: none.
- Blockers / follow-ups: complete and merge 1.4.1, then resume 1.4.2.

### 2026-11-13 — 1.4.4 dependency check

- Result / completed: checked the task row and details for 1.4.4. Implementation was not started.
- Dependencies: 1.4.3 is ⬜ in [PLAN.md](PLAN.md); the workflow dependency gate blocks this task.
  Task 1.4.3 itself depends on 1.4.2.
- Verification: inspected PLAN.md task statuses and `git status --short --branch`; main already
  had a pre-existing edit to PROGRESS.md. No application checks were run because no code changed.
- Skipped / deferred: `/dev/design` page implementation and related frontend tests are deferred
  until 1.4.3 is complete and merged.
- Failures / causes / corrections: none.
- Blockers / follow-ups: complete and merge 1.4.3, then resume 1.4.4.

### 2026-11-13 — 1.4.5 dependency check

- Result / completed: checked the task row and details for 1.4.5. Implementation was not started.
- Dependencies: 1.4.1 and 1.2.2 are both ⬜ in [PLAN.md](PLAN.md); their branches are not merged.
- Verification: inspected PLAN.md task statuses and `git worktree list` / `git branch --list
  "task/*"`; both prerequisite branches exist in separate worktrees. `git status --short --branch`
  showed pre-existing edits to PROGRESS.md on main. No application checks were run because no code
  changed.
- Skipped / deferred: OpenAPI generation, API client implementation, tests, and generated files are
  deferred until both prerequisites are complete and merged.
- Failures / causes / corrections: none.
- Blockers / follow-ups: complete and merge 1.4.1 and 1.2.2, then resume 1.4.5. The pre-existing
  dirty PROGRESS.md means the required clean-main preparation gate also remains unresolved.
