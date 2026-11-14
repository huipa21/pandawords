# Phase 7 - PWA & hardening: task details

The format for each task is Goal, Deliverables, Acceptance and Docs. Dependencies, waves and
status are in [PLAN.md](PLAN.md); a task may start as soon as its own dependencies are complete.
Read [overview.md](../architecture/overview.md), [auth.md](../architecture/auth.md),
[learning-engine.md](../architecture/learning-engine.md),
[data-model.md](../architecture/data-model.md),
[deployment.md](../dev/deployment.md), [patterns.md](../ui/patterns.md) and
[testing.md](../dev/testing.md) for existing contracts.

## Dependencies and parallel execution

- First-wave tasks **7.1.1**, **7.1.3** and **7.1.5** are independent once their PLAN dependencies
  are ✅. **7.1.2** waits for 7.1.1; **7.1.4** waits for 4.4.2. Recheck those statuses at launch.
- Use one coordinator for the phase: only that coordinator edits [PLAN.md](PLAN.md) and
  [PROGRESS.md](PROGRESS.md) on `main`, assigns task worktrees, and serializes merges, migrations,
  generated API updates and checks. Keep worktree file scopes disjoint, especially the service
  worker/app shell, security/deployment configuration and review flow.
- Apply security and performance changes to the integrated tree. Do not reduce authorization or
  relax bounds to improve benchmark results. New schema/index changes require a forward-only
  migration, a regenerated schema snapshot and tests against SurrealDB 3.3.

## Shared implementation rules

- Ordinary online review remains usable when offline functionality is unavailable. The server
  remains authoritative for exercise grading, review scheduling and durable receipts.
- Do not cache authenticated API responses, private media or user content in the service-worker
  Cache API. Explicitly selected offline review data must be stored in an owner-partitioned,
  bounded client store with lifecycle handling for logout, account changes, eviction and failed
  synchronization.
- No client-side answer, clock or local queue state may be treated as a durable review. Offline
  answers sync through server validation and the existing exactly-once receipt flow; expired,
  stale or rejected entries remain visibly unsynced and never appear as completed progress.
- Apply security headers at the appropriate web/TLS proxy boundary, retain authenticated media
  delivery, and never trust unvalidated forwarded headers. Rate limits must be explicit and
  observable without leaking credentials or private content.
- Performance work starts with a reproducible baseline and representative bounded workloads.
  Record measurements, acceptance budgets and any regressions in the directly related docs or
  [PROGRESS.md](PROGRESS.md); do not add indexes or caching based on guesses alone.
- Optional LLM, audio and image providers remain optional and are not required for offline review,
  security checks or performance tests. Use isolated fixtures and mocked providers.

## 7.1 Progressive web app and offline review

### 7.1.1 Installable PWA
- **Goal:** make the responsive web application installable on supported browsers without changing
  authentication or private-data caching semantics.
- **Deliverables:**
  - Add a valid web app manifest, versioned app icons, theme/display metadata and install/start
    behavior consistent with the existing router and login flow.
  - Add a service worker that precaches only the static application shell and versioned public
    assets. Define safe activation/update and old-cache cleanup behavior. Never precache API
    responses, authenticated media, private pages or user-specific state.
  - Add a localized, accessible install prompt that appears only when the browser supports the
    install flow and the user has not dismissed/completed it. Preserve normal browser use where
    install prompts are unavailable.
- **Acceptance:**
  - Manifest and icons validate; service-worker install, update, old-cache cleanup and offline
    application-shell fallback are tested.
  - Tests prove authenticated API responses, media and user-specific routes are not stored in
    service-worker caches; login and online routing remain functional.
  - Frontend tests cover supported/unsupported browsers, prompt dismissal, keyboard access,
    localization and responsive presentation. Production build and app-shell smoke test pass.
- **Docs:** overview.md, patterns.md, deployment.md, testing.md

### 7.1.2 Offline review queue and answer synchronization
- **Goal:** allow a learner to continue a bounded, previously prepared review session without a
  network connection and safely synchronize answers when connectivity returns.
- **Deliverables:**
  - While online, prefetch a bounded set of due cards and server-issued exercise prompts/attempts
    for offline use. Store the minimum required prompt/media data and unsynced answers in an
    owner-partitioned client store; do not expose or persist server answer keys for local grading.
  - Queue each answer against its exact server-issued attempt and stable client retry identity.
    On reconnection, submit through the existing server grader and confirmation flow; only a
    server-issued durable receipt advances authoritative review progress.
  - Define a bounded, explicit offline attempt lease compatible with the existing online attempt
    expiry contract. A prefetched attempt cannot be extended silently. Preserve queued answers
    for clear user recovery when an attempt expires, becomes stale, or cannot be synchronized;
    do not report them as graded or completed.
  - Handle duplicate/reordered sync, network loss during confirmation, account changes, logout,
    storage eviction, missing media and partial sync without duplicating receipts or losing
    unrelated queued work. Provide accessible online/offline/syncing/failed/expired states.
- **Acceptance:**
  - Browser/API tests cover prefetch bounds, offline prompt use, answer persistence, reconnect
    retries, lost responses, duplicate and reordered submissions, stale cards, lease expiry,
    storage eviction and account/logout isolation.
  - Every successful sync produces exactly one durable review receipt and uses server grading and
    timing validation. No queued, expired or rejected answer changes FSRS state or appears as
    completed; failure states retain a clear recovery path.
  - Tests prove offline storage is partitioned by authenticated user, is not put in service-worker
    caches, and contains no reusable answer key. Existing online review, audio and non-media
    exercises continue to pass.
- **Docs:** learning-engine.md, auth.md, overview.md, patterns.md, testing.md

## 7.2 Security and performance

### 7.1.3 Security hardening
- **Goal:** reduce abuse and browser-side attack surface and verify that every user-data boundary
  enforces ownership consistently.
- **Deliverables:**
  - Add bounded rate limits for authentication and resource-intensive/API operations, with
    separate treatment for authenticated users and anonymous requests. Trust client addresses
    only through explicitly configured proxies; return the repository-standard rate-limit error
    and retry guidance.
  - Add and verify appropriate security response headers and a restrictive Content Security
    Policy in the deployed web/proxy configuration. Allow only the actual required application,
    API and asset origins; document any exception rather than broadly disabling a directive.
  - Audit user-data APIs, repositories, graph edges, jobs, media and backup/import/export paths
    for independent owner checks on rows, edges and endpoints. Add or close isolation-test gaps;
    shared dictionary reads remain available only under their existing shared-data rules.
  - Document deployment/proxy assumptions, rate-limit behavior and operationally relevant
    security headers. Do not log tokens, passwords, private text, archive content or provider
    credentials.
- **Acceptance:**
  - Tests prove limits trigger at configured boundaries and recover after their window, while
    ordinary requests and trusted proxy deployments continue to work. Anonymous and per-user
    limits cannot be bypassed by spoofed forwarding headers.
  - Header/CSP tests exercise production nginx responses and required app flows in both locales;
    no broad wildcard or unnecessary unsafe directive is introduced.
  - A cross-user isolation regression matrix covers every audited user-data endpoint and its
    associated records/edges/media/jobs. No foreign-owned data can be read, changed, deleted or
    inferred through error differences.
  - `dev.ps1 check`, relevant backend/frontend suites and production configuration tests pass.
- **Docs:** auth.md, overview.md, deployment.md, testing.md

### 7.1.4 Measured performance pass
- **Goal:** improve the graph/API and initial frontend load using measured bottlenecks while
  preserving authorization, deterministic results and explicit bounds.
- **Deliverables:**
  - Establish and record reproducible baselines for representative graph queries and production
    frontend bundle output. Include dataset shape, database/runtime versions, query count or plan,
    relevant latency distribution and compressed initial JavaScript size.
  - Optimize only demonstrated graph-query bottlenecks. Add owner-aware indexes only where query
    plans and measurements support them; use a forward migration and regenerate the schema
    snapshot when schema changes are necessary.
  - Reduce unnecessary initial bundle cost through existing route/component splitting or removal
    of unused code. Preserve required localization, accessibility, offline shell and authenticated
    media behavior; do not add dependencies without need and an ADR where required.
  - Set and enforce explicit post-change performance budgets based on the measured baseline and
    target deployment, and record the actual before/after results.
- **Acceptance:**
  - Representative graph workloads at normal and maximum supported bounds return identical
    authorized nodes/edges and deterministic ordering; query counts and latency are measured
    before/after, with no silent truncation or ownership regression.
  - Any new index is migration-tested on a fresh and upgraded database and supported by query-plan
    evidence. No schema snapshot drift remains.
  - The production bundle analyzer reports the initial compressed payload and route chunks;
    the agreed initial-load budget is enforced and the target screens remain functional.
  - Focused performance regressions and the standard relevant check/build pass. Results and
    remaining bottlenecks are recorded explicitly.
- **Docs:** data-model.md, learning-engine.md, testing.md, deployment.md

### 7.1.5 Per-user FSRS parameter optimization
- **Goal:** improve scheduling parameters from an individual learner's own review history without
  mixing users' data or rewriting existing scheduling state.
- **Deliverables:**
  - Use the supported optimizer in the pinned `py-fsrs` 6.x integration over only the
    authenticated user's valid completed `review_log` history. Define minimum history,
    eligibility and re-optimization policy using the pinned optimizer's documented requirements;
    insufficient or invalid data keeps the existing/default parameters.
  - Persist optimized parameters with owner scoping and optimizer/version metadata using a
    forward-only migration if required. Validate optimizer output and apply parameters only to
    future scheduling calculations; keep desired retention independent and do not rewrite
    existing due dates, review logs or receipts.
  - Make optimization bounded and idempotent, with explicit status for unavailable,
    insufficient-history, failed and successful runs. Do not run expensive optimization on every
    review confirmation.
  - Preserve default FSRS behavior for users without valid optimized parameters and keep any
    user-facing status/action localized if exposed.
- **Acceptance:**
  - Deterministic optimizer tests use isolated per-user histories and cover insufficient samples,
    malformed/outlier logs, valid optimization, optimizer failure, persistence and repeat runs.
  - Cross-user tests prove one user's review logs or parameters cannot influence or reveal another
    user's result. Invalid output is rejected and leaves the prior valid parameters unchanged.
  - Tests prove optimized parameters affect future scheduling only; existing due dates, confirmed
    receipts, history, desired retention, theme, locale and other preferences remain unchanged.
  - Fresh/upgrade migration and schema-drift tests pass if schema changes are needed; otherwise
    tests document that persistence needs no migration.
- **Docs:** learning-engine.md, data-model.md, testing.md
