# Phase 3 - Learning engine: task details

The format for each task is Goal, Deliverables, Acceptance and Docs. Dependencies, waves and
status are in [PLAN.md](PLAN.md); a task may start when its own dependencies are complete, even
if another Phase 2 task is still running.

Read [learning-engine.md](../architecture/learning-engine.md),
[data-model.md](../architecture/data-model.md),
[components.md](../ui/components.md) and [testing.md](../dev/testing.md) for the existing
contracts. [ADR 0004](../decisions/0004-fsrs-per-user-sense.md) and
[ADR 0007](../decisions/0007-deepseek-optional-llm.md) already approve the FSRS and LLM choices.

## Shared implementation rules

- One owner-scoped card exists per user and sense, even when the sense belongs to several
  projects. Hiding or removing a membership does not erase the card or its history.
- Queue eligibility uses the effective project tree: a selected sense and its ancestors must be
  visible, and shared or user-owned content and edges must pass the existing ownership filters.
- All daily boundaries and forecast dates are UTC, consistent with the existing time convention;
  the UI converts dates for display. A first completed review introduces a card, and its project
  receives that day's new-card count. Later reviews count against the project in which they occur.
- The planning defaults below fill gaps in the current design: use the last 100 prior completed
  correct responses of the same user and exercise type for the rolling median; before 20 samples,
  use configurable fast/slow defaults of 3,000/12,000 ms for recognition and 5,000/20,000 ms for
  recall. For review cards, use equal recall/recognition weights below seven days of stability
  and 2:1 recall at or above seven days when both kinds are available. These are initial settings,
  not changes to past logs.
- DeepSeek's initial per-user budget is 20 provider attempts per UTC day, configurable with zero
  disabling calls. Cached responses do not consume it; a dispatched attempt consumes it even on
  timeout or failure. No live provider is needed for tests.
- Independent tasks can start as soon as their dependencies are met, but must coordinate shared
  files. In particular, 3.1.1 and 3.2.5 both need migrations and a schema snapshot; 3.1.3 and
  3.2.1 may also need migrations. Allocate distinct migration versions, serialize conflicting
  edits/merges, and regenerate snapshots, lockfiles and OpenAPI artifacts after integration.
- Every new user-data endpoint requires cross-user isolation tests. Use bound SurrealQL in
  `backend/app/db/`, forward-only migrations, generated API types, localized UI text and the
  existing error and design-token conventions.

## 3.1 Scheduling and daily plans

### 3.1.1 Memory and review-log migrations
- **Goal:** persist an owner's FSRS cards and review history without tying a card to one project.
- **Deliverables:**
  - Forward-only schema for `memory` and `review_log`, with the fields and indexes in
    data-model.md. A memory ID is `memory:[user, sense]`; store an owner field and every field
    needed to round-trip a py-fsrs 6.x card, plus an explicit unintroduced/introduced marker.
  - Review logs record owner, memory, project, exercise type, correctness, hint use, duration,
    auto-rating, final rating and timestamp. Include an introduction marker and an attempt
    identity suitable for exactly-once review application.
  - Index owner/due and owner/time access, and enforce the required uniqueness for memory and
    completed attempts. Project deletion must not cascade away shared cards or review history.
  - Regenerate `schema.snapshot.json`; verify SurrealDB 3.3 syntax against the test database.
- **Acceptance:**
  - Fresh-database migration and schema-drift tests pass. Required types, indexes, duplicate
    identities and owner fields are exercised against SurrealDB, not only mocked.
  - Tests demonstrate one card for a user/sense across projects, separate cards for different
    users and preserved history after a project is deleted.
- **Docs:** data-model.md, surrealdb-notes.md, testing.md

### 3.1.2 FSRS service, card creation and auto-rating
- **Goal:** create and update shared-per-user cards reliably and derive a review suggestion.
- **Deliverables:**
  - Add the approved py-fsrs 6.x dependency (`fsrs>=6,<7` on PyPI) and a typed wrapper using
    default scheduler parameters. Persist and restore the complete card state; use a per-user
    desired retention setting, default 0.9, with validation and owner-scoped read/update support.
  - Create a card for every selected sense within the existing add-to-project transaction.
    Repeated adds, a second project and hide/restore must not reset it. Reconcile existing
    selected memberships from before Phase 3 idempotently, including hidden memberships.
  - Calculate ratings from server-validated correctness, hint use and duration: wrong/gave up is
    Again; correct but hinted or slower than the slow threshold is Hard; a normal correct answer
    is Good; a fast correct recall is Easy, while the recognition auto-rating is capped at Good.
    With at least 20 samples, use 0.6 times the rolling median for the fast threshold and 1.8
    times it for the slow threshold; otherwise use the defaults above. Exactly at either
    threshold is normal. The user may override any suggested rating, including with Easy.
  - Apply the user's final rating and insert the log atomically. Enforce project membership,
    per-project daily new/review limits and an attempt's idempotency at this boundary. Concurrent
    stale reviews must not overwrite a newer card or create duplicate logs. A retry of a
    completed attempt returns its existing result; a conflicting retry is rejected.
  - Add the required user-preference schema/API changes without replacing existing preferences;
    regenerate the frontend API contract.
- **Acceptance:**
  - Tests cover card round-tripping, first add, repeat add, pre-existing memberships, rollback on
    failure, two projects sharing one card and separate users. Deleting a project preserves cards
    and logs.
  - Tests cover wrong answers, hints, both kinds, strict fast/slow boundaries, 19 versus 20
    samples, per-type/user isolation and the 60-second cap. Manual rating overrides, including
    Easy after recognition, change the FSRS update but not recorded auto-rating or correctness.
  - Concurrent/retried reviews create exactly one log and one scheduling update; new settings
    cannot be read or changed by another user.
- **Docs:** learning-engine.md, data-model.md, overview.md, testing.md

### 3.1.3 Daily plan, exam pacing and queue API
- **Goal:** build a project-scoped queue and dashboard from shared cards and actual review history.
- **Deliverables:**
  - Add an authenticated study-plan API returning plan settings, due/new counts, today's completed
    counts, the capped queue, exam pacing and a seven-day forecast. Add an owner-scoped dashboard
    API for due today, new today, 30-day retention, streak and per-project forecasts.
  - Queue due introduced cards first, lowest retrievability first, with deterministic due/ID
    tie-breaks and a documented fallback when FSRS cannot calculate retrievability. Then queue
    unintroduced senses in persisted project order. Respect hidden ancestors, daily limits and
    already completed work; paginate or otherwise bound results.
  - Provide an owner-scoped reorder operation and forward-only storage for project sense order.
    Default to existing membership order, and preserve hidden items and their ordering on
    hide/restore. Reuse the existing project update API for the complete plan settings object.
  - For an exam date, `remaining_new` is the visible unintroduced count and `days_left` is the
    number of UTC daily windows with time to study before the stored exam instant, including
    today's remaining window. It is zero when the instant has passed. Calculate
    `min(daily_new, ceil(remaining_new / max(1, days_left - 7)))` as a suggestion, not a
    replacement for the daily cap. Report when capacity before the exam instant cannot finish the
    remainder and separately when the seven-day buffer is at risk. For either instant, capacity
    is zero if it has passed; otherwise it is today's remaining allowance plus `daily_new` for
    each future UTC day that starts before that instant. This respects the existing local-date
    form's UTC timestamp instead of treating its UTC date as the user's displayed date.
  - Calculate retention as correct completed answers divided by completed answers over the last
    30 UTC dates including today; return no data rather than 0% when there are none. A streak
    counts consecutive UTC dates with a completed review, ending today or yesterday. Forecast
    actual scheduled cards over seven UTC dates including today, grouping overdue cards under
    today rather than simulating future reviews.
- **Acceptance:**
  - Tests cover empty projects, hidden ancestors, shared senses, due ordering, persisted reorder,
    zero daily limits, unlimited versus zero review cap and counts after reviewing in another
    project. Queue reads do not themselves introduce cards.
  - Exam tests cover no date, adequate/inadequate capacity, the seven-day buffer, today and past
    dates, zero limits and UTC day boundaries. For example, 20 remaining, daily limit 10 and
    12 days left suggest 4; with limit 3 and 10 days left the suggestion is 3 and only the
    seven-day buffer is at risk. Dashboard tests cover empty history, retention, streak boundaries
    and overdue/future cards in the seven-day forecast.
  - Every plan, reorder and dashboard endpoint rejects cross-user access; API types are regenerated.
- **Docs:** learning-engine.md, data-model.md, overview.md, patterns.md, testing.md

## 3.2 Exercise generation and grading

### 3.2.1 Exercise framework and attempt API
- **Goal:** generate eligible exercises, grade on the server and apply only confirmed reviews.
- **Deliverables:**
  - A typed registry for exercise generators/graders and a selector based on card state, stability
    and available prerequisites. New/learning cards use recognition; review cards use the
    recall/recognition weights above. Skip unavailable types and report when none is usable.
  - Provide shared, deterministic answer normalization and selected-lexeme form lookup for the
    recall exercises, so cloze and scenario can be implemented independently without duplicating
    grading logic. Listening may restrict answers to the form represented by its audio.
  - Authenticated APIs to create/read an attempt for an owner's visible project sense, request a
    hint, submit an answer or give up, and confirm the final rating. Use opaque IDs and the
    existing error format. Model the attempt as open, graded, then confirmed. Allow hints only
    before grading; the first answer fixes the grade, an identical retry is safe and a different
    answer for the same attempt is rejected.
  - Keep correct answers and accepted forms on the server until grading. Return only the public
    prompt/options/media before submission; return correctness, feedback and auto-rating after
    grading. Only confirmation invokes the atomic SRS update and returns a persisted receipt
    with the final rating. Duplicate submissions/confirmations are safe, while conflicting or
    stale attempts produce an explicit error.
  - Persist or otherwise verify attempt state across requests and processes, with an expiry for
    abandoned attempts. A hint request records hint use on the server.
  - Reconcile the two existing timing requirements: the client measures monotonic elapsed time
    from prompt display to submission; the server also records issuance-to-submission elapsed
    time and bounds the client value by that elapsed time and 60,000 ms before rating/logging.
    Reject invalid durations and document the resulting server-side validation.
  - Regenerate OpenAPI and frontend types; register routers without introducing live network
    dependencies.
- **Acceptance:**
  - Tests cover state-based selection, including the 1:1 and 2:1 weights below and at seven
    days, a single eligible kind and new/learning recognition. Also cover shared answer
    normalization/form lookup, missing prerequisites, no usable exercise, correct/wrong/give-up/
    hint grading, hidden or removed membership, expired attempts and repeated requests. No answer
    key, accepted-form list or correctness marker is exposed before grading.
  - Timing tests cover negative/invalid values, an implausibly long client duration, the
    60-second cap and normal client/server elapsed values. Confirming an overridden rating logs
    both ratings once, including under concurrent requests.
  - Cross-user tests cover attempt creation/read, hint, answer and confirmation; another user
    cannot read or act on an attempt. A failed operation does not mutate a card or create a
    review log.
- **Docs:** learning-engine.md, data-model.md, overview.md, components.md, testing.md

### 3.2.2 Distractor service
- **Goal:** produce plausible, safe answer alternatives from the available dictionary graph.
- **Deliverables:**
  - Rank accessible candidates in order: shared concept/domain tag, morph group, confusable
    relation, then same part of speech and frequency band. Use the data actually available from
    Phase 2; morph groups and other Phase 4 data are optional, not new prerequisites.
  - Filter shared/user-owned records and edges, exclude the answer and its synonyms in either
    direction, and deduplicate equivalent displayed options. For the frequency fallback, use
    `floor(freq_zipf)` as the initial band; treat missing or zero frequency as unknown, not as a
    match. Make selection bounded and reproducible in tests.
  - Return two to four distinct choices including the answer when enough safe candidates exist.
    Otherwise return an explicit unavailable result so another exercise can be selected; never
    invent a distractor or expose another user's content.
- **Acceptance:**
  - Tests exercise each ranking tier, frequency-band boundaries, missing tags/morphology/
    frequency, synonym exclusion, duplicate labels, insufficient candidates and deterministic
    selection.
  - Integration tests prove private senses/edges and another user's overrides cannot become
    distractors. The service works with Phase 2 data and no LLM.
- **Docs:** learning-engine.md, data-model.md, lexicon-pipeline.md, testing.md

### 3.2.3 Recognition exercises
- **Goal:** implement definition-to-word, word-to-definition and relation quizzes.
- **Deliverables:**
  - Register `def2word`, `word2def` and `relation` as recognition exercises using effective
    user-visible definitions/glosses and the distractor service.
  - Use the existing pronunciation metadata for word-to-definition and accessible relation or
    derivation edges for relation prompts. Generate a relation question only when the edge,
    answer and sufficient safe choices exist.
  - Shuffle public choices without exposing the answer key, and grade against the server's
    attempt state. Fall back to another eligible type when content is insufficient.
- **Acceptance:**
  - Tests cover all three types, multiple senses/overrides, correct and incorrect choices,
    option uniqueness, missing pronunciation/relations and insufficient distractors.
  - Synonyms cannot be incorrect alternatives, and private relations or overrides do not leak
    between users. Recognition's automatic rating never exceeds Good.
- **Docs:** learning-engine.md, components.md, testing.md

### 3.2.4 Cloze and listening exercises
- **Goal:** add offline-capable typed recall using examples and authenticated pronunciation.
- **Deliverables:**
  - Register `cloze` and `listen` as recall exercises. Cloze uses a source example containing an
    accepted word form, with that form blanked without exposing it elsewhere in the prompt.
    Listen uses available audio for the user's preferred accent via the existing media API.
  - Reuse the framework's answer normalization and form lookup: grade cloze against the lemma
    and valid forms of the selected lexeme, and listening against the spelling represented by
    the audio, not an unrelated inflection. Missing examples, forms or audio make only that
    type unavailable.
  - Reuse the authenticated audio flow and avoid exposing filesystem paths or other users' media.
- **Acceptance:**
  - Tests cover accepted cloze inflections, listening spelling, case/whitespace, incorrect
    answers, punctuation and substring-safe cloze blanks. An example without an accepted form is
    skipped; an unspoken inflection does not pass listening.
  - Tests cover both accents, inaccessible/missing audio and fallback to another eligible type.
    No external audio or LLM service is required in tests.
- **Docs:** learning-engine.md, lexicon-pipeline.md, components.md, testing.md

### 3.2.5 Optional DeepSeek client
- **Goal:** provide a single bounded, cached and optional JSON-mode LLM service.
- **Deliverables:**
  - Implement the approved OpenAI-compatible DeepSeek client in `services/llm.py`, with typed
    JSON validation, configured model/base URL, bounded timeouts and explicit unavailable/error
    results. A missing or example-placeholder key disables calls.
  - Add the approved `openai` dependency, configuration and `.env.example` entries as needed.
    Persist cache entries and per-user daily budget accounting with forward-only schema changes;
    reserve each provider attempt atomically before dispatch, including retries.
  - Key cache entries by canonical input, model and prompt/schema version. Share only results
    derived from shared content; owner-scope any user-specific content. Do not log keys, prompts,
    answers or personal notes.
  - Cache hits work without a provider call; failed or invalid responses do not poison the cache.
    Validate caller-specific content before caching it. Missing configuration, exhausted budget,
    timeouts and provider errors leave non-LLM features usable and provide an observable reason
    to the caller.
- **Acceptance:**
  - Mocked tests cover valid and invalid JSON, cache hit/miss and versioning, disabled keys,
    provider failure/timeout, zero/exhausted budgets, UTC reset and concurrent reservations.
    Provider attempts cannot exceed a user's configured daily budget.
  - Tests verify shared versus owner-scoped caching and absence of secrets/private data in logs.
    No test contacts DeepSeek; exercise-level fallback is verified by 3.2.6 and 3.3.2.
- **Docs:** learning-engine.md, overview.md, setup.md, testing.md

### 3.2.6 Scenario exercise
- **Goal:** offer a cached scenario-to-word recall exercise when DeepSeek is available.
- **Deliverables:**
  - Register `scenario` using the framework and LLM service. Generate and validate a short
    scenario for the selected sense; grade accepted forms locally with the framework's shared
    normalization/form lookup, not with an LLM call.
  - Use the existing worker/job pattern for cache misses so a slow provider does not block the
    review session. Cache shared-content results under a versioned key and keep custom/private
    inputs owner-scoped; never send notes or another user's data.
  - Use a valid cached scenario even when the provider is disabled. On a cache miss, until
    generation succeeds or when the provider is disabled, exhausted or fails, skip this type
    and select another available exercise with an observable reason.
- **Acceptance:**
  - Mocked tests cover successful generation, malformed or answer-revealing scenarios, cache
    reuse, concurrent/repeated requests, job failure and all optional-provider fallbacks. Use
    a fake registry type when testing independently of the other exercise implementation tasks.
  - Scenario answers follow the same accepted-form grading, timing, rating and ownership rules
    as other recall exercises; no real network call is required.
- **Docs:** learning-engine.md, overview.md, components.md, testing.md

## 3.3 Review UI and end-to-end verification

### 3.3.1 Shared exercise components
- **Goal:** provide reusable, accessible exercise and rating controls.
- **Deliverables:**
  - Implement `ExerciseShell`, `ChoiceGrid`, `TypedAnswerInput`, `RatingBar` and
    `ReviewProgress` in `src/components/exercise/`, using the component catalogue and tokens.
  - Emit the answer, client elapsed time and hint intent; display correctness and auto-rating
    returned by the server rather than deciding them in the component. Support 2-4 choices,
    typed-answer feedback, rating override, progress and the documented keyboard shortcuts.
  - Add representative states to `/dev/design`, both locales, responsive layouts and accessible
    labels/focus behavior. Update the component contract if the existing event shape differs.
- **Acceptance:**
  - Component tests cover choice/keyboard interaction, typed input, hint and feedback states,
    preselected/changed rating, disabled submitting and progress. Choice and rating shortcuts
    are scoped so one keypress cannot select both.
  - Preview works in light/dark themes and at mobile/desktop widths; all visible text is
    localized and no raw colors or sizes are introduced.
- **Docs:** components.md, patterns.md, testing.md

### 3.3.2 Review session page
- **Goal:** complete a project review from its queue through confirmed FSRS updates.
- **Deliverables:**
  - Replace the `/projects/:id/review` placeholder with a queue-driven session using the plan,
    attempt and confirmation APIs and shared components. Render recognition and typed recall
    generically, so the optional scenario type needs no separate page dependency.
  - Show feedback and the suggested rating, allow an override before continuing, then refresh
    progress from confirmed results. Handle loading, empty, unavailable, stale, expired and
    recoverable error states without silently skipping a card.
  - Prevent duplicate submits, handle retries/navigation safely and keep already confirmed
    reviews durable. Use existing routing, generated API types, i18n and responsive patterns.
- **Acceptance:**
  - Frontend tests cover recognition and recall, give-up/hint, manual rating, queue exhaustion,
    no usable exercise, retry/stale responses and duplicate-submit protection.
  - A session works without DeepSeek and with missing optional audio; a confirmed review is not
    applied again after refresh or retry. Both locales and mobile/desktop layouts work.
- **Docs:** learning-engine.md, components.md, patterns.md, testing.md

### 3.3.3 Plan settings and dashboard
- **Goal:** make pacing and review progress understandable and editable.
- **Deliverables:**
  - Replace the project plan placeholder with settings and project summary; reuse the existing
    project form/API and preserve all plan fields when submitting the replacement plan object.
    Expose the per-user desired retention setting separately from per-project settings.
  - Show due/new counts, exam suggestion and capacity warnings, 30-day retention, streak and
    seven-day project forecasts. Provide controls to reorder new senses and links into review.
  - Connect the global `/review` entry to the dashboard/project selection. Cover loading, empty,
    no-history and error states with bilingual, accessible, responsive UI.
- **Acceptance:**
  - Frontend tests cover settings validation/save/clear, preserving untouched values, reorder,
    zero limits, past/unachievable exams, no-history metrics and API errors.
  - Data and settings stay scoped to the signed-in user; changing desired retention does not
    silently rewrite existing card history.
- **Docs:** learning-engine.md, components.md, patterns.md, overview.md, testing.md

### 3.3.4 Review-session E2E
- **Goal:** prove the review workflow against the real local stack without external services.
- **Deliverables:**
  - Add a Playwright flow using the fixture lexicon and a uniquely created test learner/project.
    Add enough fixture senses for safe recognition choices, open the plan and start a review;
    use a known fixture answer without exposing the server's answer key.
  - Answer a question, verify feedback and the suggested rating, change the rating, confirm it,
    and verify the persisted receipt and updated queue/progress after a reload and retry.
  - Run with DeepSeek disabled and external audio disabled; use existing test selectors,
    credentials, cleanup and local-stack conventions.
- **Acceptance:**
  - The browser flow passes against the local API and SurrealDB, without network downloads,
    live LLM or audio providers. It verifies the final rating and a single increase in completed
    count even after a retry; backend integration tests verify the single review-log row.
  - Relevant backend/frontend tests and `dev.ps1 check` pass; run the explicit E2E selector and
    record actual results. Delete only the test's project and disable only its learner, including
    on failure. The disabled user and their retained history remain because no user-delete API
    exists; never wipe the development database.
- **Docs:** testing.md, learning-engine.md

## Phase exit

- All Phase 3 tasks meet their criteria, are merged, and have their statuses and verification
  recorded using the existing workflow.
- Review works without DeepSeek: project queues respect visibility and limits, rating overrides
  persist once, and the same user/sense card is shared across projects without crossing owners.
- Run `.\scripts\dev.ps1 check`, `.\scripts\dev.ps1 test -Backend -Frontend`, and the explicit
  `.\scripts\dev.ps1 test -E2E` against the fixture-backed local stack. Record any failure or
  skipped check rather than marking it passed.
