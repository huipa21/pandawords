# Learning engine

### Morphology discovery contract (4.3.2)

Existing morphology distractor ranking consumes materialized `morph_group` sense memberships;
no exercise consumer should derive groups from matching word fragments. The service functions
`morphology.read_morphemes(db,user,lexeme_id)` and
`read_group_members(db,user,target_id,table,limit=100)` accept opaque IDs. Group targets are
sense/morpheme only, candidates are deduplicated and deterministically ID-sorted, and limits
are bounded to 1–300. All relation/endpoint/tag owners are checked independently; unrelated
tag kinds and hierarchy members are excluded. Missing analyses/groups are ordinary empty
results, not a reason to guess candidates or invoke an LLM during exercise selection.

## Unit of memory

One FSRS card per **(user, sense)**, stored as `memory:[user, sense]`. A phrase's senses are cards
too. A sense included in several projects shares one card. Reviewing it from any project updates
the same memory.

## Scheduling (py-fsrs 6.x)

- `Scheduler` with default parameters at first. Per-user parameter optimization (from `review_log`)
  comes later.
- Desired retention: per-user setting, default 0.9.
- A new card is created in the add-to-project transaction for each selected sense. It remains
  unintroduced until its first completed review. Repeat adds, second projects and hide/restore
  never reset it. `srs.reconcile_memberships(db, owner)` backfills pre-Phase-3 selections,
  including hidden memberships, atomically and idempotently; daily-plan callers must run this
  before reading a legacy queue. `srs.read_memory` also reconciles when the requested card is absent.
- `GET/PATCH /api/auth/me/srs-preferences` reads/updates only the authenticated user's
  `desired_retention` (strictly between 0 and 1, default 0.9), preserving theme/locale/accent.
  The scheduler reads this setting at confirmation, without rewriting existing due dates.

## Auto-rating (the user can change the rating before moving on)

Exercises are either **recognition** (choose from options) or **recall** (type or produce).

| Outcome | Recognition | Recall |
|---|---|---|
| Wrong / gave up | Again | Again |
| Correct but slow (> slow threshold) or used a hint | Hard | Hard |
| Correct, normal time | Good | Good |
| Correct and fast (< fast threshold) | Good (capped) | Easy |

- The thresholds use the last 100 prior completed correct responses of the same owner and exact
  exercise type: median × 0.6 (fast) / × 1.8 (slow), after at least 20 samples.
  Defaults are recognition 3,000/12,000 ms and recall 5,000/20,000 ms, configurable through
  `SRS_RECOGNITION_FAST_MS`, `SRS_RECOGNITION_SLOW_MS`, `SRS_RECALL_FAST_MS` and
  `SRS_RECALL_SLOW_MS`. Fast must not exceed slow; both boundaries themselves are normal.
- Response time is measured on the client from when the prompt is shown to when the answer is
  submitted. It is capped at 60 s.
- `review_log` stores `auto_rating`, the final `rating` and `duration_ms`.

### Trusted framework integration

`srs.read_memory(db, owner, sense_id) -> MemoryRead` provides the complete card and a
content-derived `version`. Capture this version when issuing an attempt, not at confirmation.
Only the exercise framework supplies `FrameworkGrade(exercise, kind, correct, gave_up,
hint_used, duration_ms)` after server grading and elapsed-time validation; this is not an HTTP
request model. The SRS wrapper rejects negative/noninteger duration and caps at 60,000 ms.

`srs.grade_review(db, settings, owner, *, attempt_id, project_id, sense_id, expected_version,
grade) -> GradedReview` checks effective tree eligibility and fixes the suggestion from prior
history. Persist this immutable object in the server-owned attempt. The client may supply only
its final rating to the framework's confirmation endpoint.

`srs.apply_review(db, owner, review: GradedReview, rating: Rating, *, now=None) -> ReviewReceipt`
rechecks owner, selected sense and visible ancestors/edges, the issuance version, UTC daily
limits and retention inside one retryable transaction. The card, completed log and receipt
commit together. A project revision write serializes capacity across different cards; a stale
card fails with `srs.stale_review`. Identical completed retries return the original persisted
receipt even after later reviews or project deletion; changed completion data fails with
`srs.attempt_conflict`. Wrong/give-up correctness stays false even with a manual Easy override.

The first review consumes the introduction project's UTC new allowance. Every later review,
including same-day learning repetitions and reviews in another project, consumes that review
project's allowance. A null review cap is unlimited; zero disables that category.

## Exercise types (Phase 3)

| Type | Kind | Prompt → answer | Needs |
|---|---|---|---|
| `def2word` | recognition | definition (or Chinese gloss) → choose the word | distractors |
| `word2def` | recognition | word + pronunciation → choose the definition/gloss | distractors |
| `relation` | recognition | "Antonym / synonym / derived form of X?" → choose | relates_to / derives_to edges |
| `cloze` | recall | sentence with a gap → type the word (any accepted form) | example sentence |
| `listen` | recall | audio (user's accent preference) → type the spelling | audio |
| `scenario` | recall | DeepSeek-generated scenario → type the word | LLM (cached) |

Later: `image2word` (Phase 5) and `produce` (write a sentence, graded by DeepSeek).

**Distractors** come from the graph, in this order: senses with the same concept/domain tag →
the same morph group → `confusable` relations → the same POS and frequency band. A distractor can
never be a synonym of the answer.

`services.distractors.choices(db, context, *, label="word" | "definition", count=4,
rng=None)` implements this offline provider. Capture the DB and label in a closure for
`DistractorProvider`. Definition labels use the effective English `definition`, falling back
to the effective `gloss.zh`, `gloss.zh-CN`, then `gloss.en`; word labels use effective lemma `text`.
Other senses displaying the same headword cannot be incorrect definition alternatives.
The result is `DistractorCandidates` (including the answer's private `answer_choice_id`) or
`Unavailable`. `select_choices(pool, ...)` is the pure typed selection seam.

Discovery considers up to 64 rows per tier in stable edge-ID order, uses accessible
`member_of` concept/domain or optional morph-group tags, then bidirectional `confusable`
edges and same-POS lemma frequency. Frequency bands are `floor(freq_zipf)`; missing, zero,
negative and non-finite frequencies never match. No morphology or LLM prerequisite is added.
All records, ancestry edges, semantic edges and tags must be shared or owned by the learner;
only that learner's effective overrides affect labels. Synonyms in either direction and
equivalent displayed labels (Unicode NFKC, case and whitespace normalized) are excluded,
including alternate accessible spellings of synonym senses. Selection preserves tier priority,
returns two to four choices when possible, and shuffles their positions with an injectable RNG.
Oversized synonym/ancestry safety sets fail closed. Bounded discovery may report unavailable
instead of searching the whole dictionary; it never invents options.

### Recognition plugins (3.2.3)

`services.recognition.register(target, recognition.DatabaseProvider(db))` installs `def2word`,
`word2def` and `relation` into the supplied typed registry. The application bootstrap calls this
alongside the recall/scenario registration hooks; importing the module has no global side effects.
`RecognitionProvider` supplies labeled distractor choices and accessible `RelationQuestion`s,
so offline fixtures can replace acquisition without replacing grading or attempt persistence.

Definition-to-word uses the selected sense's effective meaning, not another sense of its lemma.
Word-to-definition includes the selected lexeme's POS and available accent/IPA in `prompt.text`;
missing pronunciation is valid, and no new pronunciation is fetched or synthesized.
Relation prompts explicitly name the stored edge type and its direction relative to the selected
sense/lexeme. Accessible `relates_to` and `derives_to` targets require visible ancestry and effective
content. Other known answers for the same relation/direction and the source headword are removed
from alternatives, in addition to the distractor service's bidirectional synonym exclusions.
Discovery is bounded to 64 edges/answer contexts and oversized safety sets fail closed.

Every generated question independently shuffles choices and replaces record IDs with random opaque
IDs. The correct ID and displayed feedback answer exist only in the persisted private `AnswerSpec`;
the shared registry grader compares submitted IDs, never client correctness or displayed labels.
Missing meanings, relations or two safe distinct options return `Unavailable` for framework fallback.
No new schema or transport types are required. Automatic recognition ratings remain capped at Good;
manual Easy confirmation remains supported.

**Choosing an exercise type**: new or learning cards get recognition types. Cards in review get
mostly recall types as stability grows. Types whose requirements are missing (no audio, LLM off)
are skipped.

### Exercise framework and durable attempts (3.2.1)

`services.exercise_registry.ExerciseRegistry.register(ExercisePlugin(exercise, kind,
generate, grade))` registers one unique stable type ID. `generate(context: ExerciseContext)`
is async and returns `GeneratedExercise(prompt: ExercisePrompt, private: AnswerSpec)` or
`Unavailable(exercise, reason)`; the synchronous grader takes `(AnswerSpec, answer: str)` and
returns `ExerciseFeedback(correct, answer)`. Plugins import the domain and registry contracts,
not the attempt service. Register plugins at application composition time; this framework
intentionally ships **no placeholder production generators**. Request-bound
`exercise_recall.build_registry(db, settings, accent)` adds concrete `cloze` and `listen`
plugins to the base registry for API creation and grading. New/learning cards still need a
recognition plugin; otherwise creation returns `409 exercise.no_usable`.

The context contains effective owner-visible lemma/selected lexeme/sense records and normalized
`forms`. It is resolved through visible selected ancestry, not by searching every lexeme of
a headword. `DistractorProvider`, `ClozeProvider`, `ListeningProvider` and `ScenarioProvider`
protocols return their corresponding concrete domain source models or `Unavailable`.
Recognition uses public `Choice(id, label)` values and a **private** `choice_id`.
Cloze/scenario use private `accepted_forms`; listening sets `restriction="audio_form"` and
`answer` to the form represented by its protected `media_id`, never all inflections.
Provider closures may capture configured DB/settings dependencies; the registry has no network
or provider imports.

Selection first skips incompatible states/prerequisites, then chooses a **kind**, then a type
uniformly within that kind. New/unintroduced, Learning and Relearning use recognition only.
Introduced Review uses recall:recognition **1:1 below seven days**, **2:1 at/above seven**.
A sole usable kind receives all weight. Skips are returned on successful attempts; no-usable
errors include the reasons in the existing error message and structured `exercise_no_usable`
log. A seeded/injected random callable makes boundaries reproducible.

`normalize_answer` performs Unicode NFKC, curly apostrophe/quote and nonbreaking hyphen folding,
casefolding and whitespace collapse/trim. It does **not** stem, remove punctuation/accents or
accept arbitrary related words. `selected_lexeme_forms(lemma, lexeme)` returns sorted unique
normalized headword + that effective lexeme's forms. `grade_answer` compares whole normalized
recall answers; choice IDs use exact matching. Listening's audio-form restriction is separate
from this common normalization.

### Optional image recall and review media (5.1.3)

The request-bound production registry also registers `exercise_image` as recall `image2word`.
It sorts the learner's exact-sense image IDs, reauthorizes each local record/path and validates
the current encoded file and every frame using the upload validator. Missing, deleted, corrupt,
foreign-owner or wrong-target candidates are skipped independently. No provider/LLM call occurs.
The first usable image is stable until its eligibility changes. Grading reuses the selected
lexeme's private normalized forms and local grader, including give-up and receipt semantics.

The public image prompt contains an opaque protected media ID, blank generic text and optional
safe attribution; the client supplies localized generic wording/alt text. Creator/source credit
is retained verbatim only when it does not contain any selected answer form (including normalized
Unicode, HTML entities and URL encoding). Otherwise the image is skipped rather than suppressing
required credit. Pixabay rows without attribution are also unavailable.

`GET/PATCH /api/auth/me/review-preferences` reads/updates only the current learner's strict boolean
`review_images_enabled` / `review_audio_enabled` (default true), and existing `accent` (`US`/`UK`).
PATCH is nonempty, non-null and partial; it preserves theme, locale and desired retention.
New attempt selection skips `image2word`/`listen` when disabled; grading always retains the full
registry, so toggling or deleting an image after issuance does not invalidate its private answer
or confirmation. New/learning recognition and existing review-kind weights are unchanged.

### Offline recall (3.2.4)

`exercise_cloze.register(registry, provider)` first tries confirmed owner-private sentence
contexts linked to the reviewed sense (4.4.4), then effective selected-sense examples.
The request-bound provider reads only same-owner `used_in` edges and sentence endpoints.
Hidden sentence memberships in the selected project, deleted links/endpoints and stale,
invalid or nonmatching spans cannot supply a prompt. Discovery is deterministic and bounded
to 64 links/hidden memberships; oversized contexts fall back to source examples.
Private contexts are never written to shared caches, and public attempts expose only the
masked text, not sentence/link IDs, source, translation or answer spans.

Private sentence spans are half-open original Unicode code-point offsets. Validation and
masking map normalized matches back to the original text, preserving casing, whitespace,
combining characters and emoji outside the blanks. All repeated/inflected accepted forms
are masked, not only the linked occurrence. Invalid context falls back without LLM use.
Grading, timing, private answer storage and exactly-once SRS confirmation are unchanged.

Without a private context, cloze normalizes the
sentence with the shared answer contract, matches whole forms (not substrings of other words),
prefers longer overlapping forms, and replaces **every** accepted-form occurrence with `____`.
The prompt contains only that blanked sentence; it never includes definitions or translations
that might reveal another answer. Empty forms and examples without a match are unavailable.
All selected-lexeme forms plus the lemma remain acceptable, not just the blank's original form.

Distractor morphology discovery reuses the bounded, owner-safe morphology group reader;
only validated `morph_group` sense memberships qualify, never matching word fragments or
arbitrary tag kinds/morpheme labels. Effective owner-visible concept/domain memberships
still rank first, followed by morph groups, confusable edges, and POS/frequency fallback.
Every relation and both endpoints are authorized separately. Synonym exclusions, stable
tier/ID ordering, at most four choices, and fewer-than-two-safe-choices unavailability remain.

`exercise_listen.register(registry, provider)` uses a typed `ListeningProvider`. Its production
provider captures DB/settings and the authenticated user's preferred US/UK accent. It checks
existing effective pronunciation references through `media.read`, requiring accessible local
audio targeting this exact lexeme and matching the requested accent. No other-accent fallback,
download, synthesis, job or LLM call happens during exercise creation. The recording represents
the canonical stored lemma spelling, not a user's renamed headword or an unspoken inflection;
if that spelling is no longer an accepted selected form, listening is unavailable.
Only the opaque media ID appears in the otherwise empty listening prompt. The shared grader
uses `audio_form` restriction for spelling, while retaining normal case/space/punctuation folding.
Missing/private/broken audio skips only listening; missing examples skip only cloze, leaving
other state-eligible plugins available. Both concrete types use the durable attempt flow.

Attempts have opaque random IDs and persist `open → graded → confirmed`, expiring **30 minutes
after issuance** while unconfirmed. Create/read/hint/answer/giveup/confirm are owner-scoped;
unconfirmed operations recheck effective membership, existence and the issuance `MemoryRead.version`.
An expired attempt is `410 exercise.expired`; stale memory is `409 exercise.stale`; hidden or
removed membership is explicitly ineligible. Only open attempts accept hints; a successful hint
is persisted before returning it, retries are safe, and missing hints return `exercise.hint_unavailable`.

The first submission stores its exact answer/give-up + client-duration fingerprint,
`FrameworkGrade`, feedback and the `srs.grade_review` result. Identical retries return that
grade; changed answers, give-up intent or durations return `409 exercise.answer_conflict`.
There is no scheduling write until confirmation supplies the final rating to `srs.apply_review`.
That boundary atomically saves the card, review log and receipt; marking the attempt confirmed
is recoverable from the durable receipt after a process interruption. Conflicting confirmations
fail. Confirmed receipt reads/retries remain valid after expiry, later reviews or project
deletion; unconfirmed abandoned/stale attempts do not.

The shell measures monotonic elapsed milliseconds with `performance.now()` from prompt display
to submit and sends a nonnegative **integer** `duration_ms` (floor before submission). The server
rejects negative, boolean, string, fractional and nonfinite durations; records issuance-to-answer
`server_elapsed_ms`; and rates/logs `min(client_duration_ms, server_elapsed_ms, 60000)`.
Thus a client displaying a prompt late may report less elapsed than the server, but cannot claim
more than server elapsed or exceed the one-minute cap. Identical retries do not recompute timing.

## Daily plan (per project)

### Optional JSON generation (3.2.5)

`services.llm.generate_json(db, settings, user=..., response_model=..., prompt=...,
prompt_version=..., schema_version=..., inputs=..., validate=...)` returns typed
`LlmResult(value, cached)`. Prompts and versions are trusted application constants; private
notes, overlays and learner context belong only in `inputs`, which is owner-scoped by default.
For reusable scenarios pass `inputs=None, shared_sources=(lemma_record, lexeme_record, sense_record)`:
the service reads only shared dictionary lemma/lexeme/sense fields, never user overlays.
Missing/private sources or mixing shared sources with arbitrary inputs is `invalid_scope`.

Always supply a caller validator for scenario constraints (answer leakage, target/form
compatibility, etc.). It runs before caching **and** before returning a cache hit. Rejected,
malformed, extra/incorrectly typed fields, truncated and failed responses never enter the cache.
Version prompt/schema changes explicitly; the canonical key also includes actual input,
prompt, model, base URL and generated JSON schema.

Catch `core.errors.LlmUnavailable` and inspect `.reason`: `disabled`, `budget_exhausted`,
`timeout`, `provider_error`, `invalid_response`, `rejected_response`, `storage_error`,
or `invalid_scope`. Workers should skip/fall back rather than make learning depend on the LLM.
### Cached scenario recall (3.2.6)

`services.exercise_scenario.register(registry, provider)` installs `scenario` as recall.
Bind `services.scenario.acquire(db, settings, context)` as its `ScenarioProvider` at registry
composition. It probes the persistent, validated LLM cache with dispatch disabled; a cache hit
works with a missing key or zero budget. A miss never calls the provider during a review.
Instead, an owner/project/content-version/UTC-day-scoped, deduplicated `scenario` job is queued and
selection skips this type with `generation_pending`, choosing another eligible exercise.

The worker reloads owner-visible selected ancestry, rejects changed content (`stale_content`),
and calls only `services.llm.generate_json`; its existing atomic budget and bounded retries
apply. Expected unavailable results terminate the job with the public-safe LLM reason
(`disabled`, `budget_exhausted`, `timeout`, `provider_error`, `invalid_response`, etc.).
The same terminal job is reused for that UTC day rather than dispatching repeatedly; a later
day can retry after budget reset or provider recovery without invalidating good cache entries.
Unexpected failures retain
the generic worker's bounded retries. The next selection reports that reason; jobs whose cache
is missing despite completion report `cache_unavailable`. Storage failure skips only scenario.

Shared caching is used only after effective selected fields match verified shared records;
the LLM service independently rereads those shared sources. Custom senses and changed overlays
use owner-scoped input/cache entries. Only headword, selected POS/forms and definition/gloss
are copied into private inputs: no notes, unrelated learner context or foreign records.
Jobs contain only project/sense IDs and a versioned digest, never prompt/input text.

The response schema accepts only a 20–400-character scenario. Validation rejects malformed,
markup/control/multiline/blank/clue content, overlong sentence sequences, and normalized
headword or selected-lexeme form leaks, including separated spellings. Validation runs before
caching and again on reuse. The public prompt is plain text; accepted forms remain private.
All answers are graded locally by `grade_answer`, using `selected_lexeme_forms`; no LLM
grading occurs. Durable ownership, timing, rating and confirmation rules remain unchanged.

- `plan.daily_new`: the maximum number of new senses introduced per day.
- `plan.exam_date` (optional): suggested daily new = ceil(remaining new ÷ max(1, days left − 7)),
  capped by `daily_new`. The UI shows when the plan can't finish before the exam.
- `plan.review_cap` (optional): the maximum number of reviews per day. Overdue cards are ordered by
  retrievability (lowest first).
- Queue order: due reviews first, then new senses in project order (the user can reorder).

### Planning API (3.1.3)

`GET /api/projects/{id}/study-plan?offset=0&limit=100` returns settings, visible due-now and
unintroduced counts, completed UTC-today introduction/review counts, remaining allowances,
the capped queue, exam pacing and seven forecast dates. Queue pages allow offsets 0–10,000
and limits 1–500; `queue_total` is the size after daily caps, before pagination. Counts are
not reduced by pagination. A null review cap is unlimited; zero disables its category.
Same-day learning repetitions remain eligible when scheduled due again, consuming review
capacity rather than a second introduction. Each item contains `memory`, `memory_version`
(the issuance fingerprint) and optional `retrievability`; confirmation still belongs to the
trusted exercise framework, not this read API.

Eligibility reuses selected memberships, independently visible lemma/lexeme/sense ancestors,
and shared/requester-owned content **and** graph edges. Legacy cards are reconciled without
introducing them. Due introduced cards sort by ascending actual FSRS retrievability, then due
instant and opaque sense ID. Missing/nonpositive stability, missing last review, calculation
errors or nonfinite/out-of-range results use a conservative sorting value of zero and expose
`retrievability: null`; ties still use due/ID. New cards follow persisted membership order.

`PUT /api/projects/{id}/study-plan/order` accepts `{sense_ids: [...]}` containing every
effectively visible selected sense exactly once. It replaces only visible slots in the full
order, keeping hidden senses (including hidden ancestors' descendants) in their original slots.
It returns the complete order including hidden items. Missing/extra visible IDs are a
`409 study.invalid_order`; duplicate IDs are invalid input. Initial order is membership
`added_at`, then membership ID. Reordering persists all slots; future additions append.
Use the existing `PATCH /api/projects/{id}` with a **complete** `plan` to change settings.

Exam pacing honors the stored UTC **instant**, including local-midnight timestamps.
`days_left` counts today's remaining window plus future UTC dates starting strictly before
the exam; it is zero at/past the instant. The suggestion is
`min(daily_new, ceil(remaining_new / max(1, days_left - 7)))`, never a new cap.
Capacity is today's unspent new allowance plus a daily allowance for each such future date,
or zero at/past the instant. `impossible` compares remaining new with exam capacity;
`buffer_at_risk` independently compares it with capacity before the instant seven days earlier.
For 20 remaining/10 daily/12 windows the suggestion is 4; 20/3/10 suggests 3 and risks only
the buffer. A future midnight contributes no window on that midnight's date.

## Project review session (3.3.2)

`/projects/:id/review` reads the first queue entry from the authenticated study-plan endpoint,
then creates a durable attempt for its sense. The page renders only the generated prompt contract:
ordered opaque choice IDs for recognition, or literal prompt text and typed input for recall
(including optional scenario prompts). It never grades, constructs answer keys, or requires DeepSeek.
Protected media uses the existing authenticated blob/playback adapter; unavailable playback is
explicit and does not prevent retry, give-up or exit.

Answers/give-ups persist their exact body, including monotonic duration, before transport.
Feedback and suggested ratings come exclusively from the server. Manual overrides are persisted
before confirmation, and only a confirmed receipt advances to a refreshed queue/progress snapshot.
An uncertain confirmation retries the same rating; a recovered confirmed receipt never posts a
second review. Completed attempt IDs and the active attempt/pending request live in owner/project
scoped **sessionStorage**, not localStorage, and survive navigation/reload in the same tab.
Storage failures block mutations rather than losing retry identity. No credentials or private
answer specifications are stored; pending learner answers remain until resolved.

The fixture-backed real-stack browser contract (`frontend/e2e/review-session.spec.ts`, 3.3.4)
starts review through the project plan and answers a new `schedule` sense using known fixture
content plus the public exercise type. Same-POS/frequency-band fixture nouns supply safe
distractors with LLM and external audio disabled. It verifies server feedback/auto-rating,
a different final rating, and the same durable receipt after reload and identical confirmation
retry. A one-new-card allowance makes queue exhaustion and exactly one completed introduction
observable even though three unintroduced senses remain. Session progress survives reload;
public attempt readback proves receipt retention independently of sessionStorage. Existing SRS
integration tests additionally assert the single review-log row under retry/concurrency.
The browser flow's execution status is recorded separately in `docs/dev/testing.md`.

No-usable exercises stay on the selected card without silently advancing. Expiry, stale/conflicting
state and unavailable membership require explicitly reloading the queue for a fresh attempt.
Recoverable failures retain the request and retry action. Exiting an active session requires
confirmation; disposal/project/owner changes invalidate late responses and stop protected audio.

## Dashboard

### Frontend planning surfaces (3.3.3)

`/review` is the authenticated, owner-scoped dashboard/project picker. It distinguishes
deduplicated due-today/available-new totals from each project's unintroduced count, shows
completed UTC-today counts, nullable 30-day answer retention, the streak and seven scheduled
UTC dates. Zero retention is a real result, not the no-history state. Each project links to its
plan and review route.

`/projects/:id/plan` uses the existing project form and complete replacement `plan` object.
Untouched fields (including the original exam instant) survive saves; clearing the exam/review
cap sends explicit nulls, and zero pauses a category. Exam capacity/buffer warnings come from
the server rather than a second client calculation. Personal desired retention is a separate
preferences form and PATCH; it never submits card/history changes.

Priority editing loads **all** visible project-tree pages, independently of capped study queues,
and submits every visible selected sense once. The existing API has no order-read endpoint:
the UI explicitly starts a new draft in tree order, not a purported saved-priority readback.
Only an explicit changed-draft save replaces priority. Returned hidden IDs are excluded from
the editor; the server preserves hidden slots. Selection conflicts keep the draft and prompt
an explicit reset/reload. Already introduced senses remain introduced.

Due today, new today, retention over the last 30 days, a streak, and a per-project forecast for the
next 7 days.

`GET /api/dashboard` deduplicates shared cards across the owner's visible projects. Due today
includes overdue cards and cards scheduled later on today's UTC date. New today is the maximum
number of distinct visible unintroduced cards assignable to projects' remaining new allowances;
shared cards never consume two introductions. Project forecasts retain their own memberships,
plan pacing and completed counts. Owner totals include completed history even after a project
is deleted. Retention is correct/completed answers over the last 30 UTC dates including today,
or null without answers. Streak ends today or yesterday. Forecasts contain seven UTC dates,
bucket overdue cards under today and use actual introduced-card due dates, never simulated
reviews. Planning snapshots explicitly reject oversized trees, over 1,000 projects or over
100,000 completed history rows with 413 rather than silently returning incomplete counts.
