# Learning engine

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
intentionally ships **no placeholder production generators**. Until 3.2.3/3.2.4/3.2.6 register
real generators, creation returns `409 exercise.no_usable`, without calling a provider.

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
For reusable scenarios pass `inputs=None, shared_sources=(lemma_record, sense_record)`:
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
This task provides the client contract; scenario job registration and exercise fallback are
implemented by 3.2.6/3.3.2.

- `plan.daily_new`: the maximum number of new senses introduced per day.
- `plan.exam_date` (optional): suggested daily new = ceil(remaining new ÷ max(1, days left − 7)),
  capped by `daily_new`. The UI shows when the plan can't finish before the exam.
- `plan.review_cap` (optional): the maximum number of reviews per day. Overdue cards are ordered by
  retrievability (lowest first).
- Queue order: due reviews first, then new senses in project order (the user can reorder).

## Dashboard

Due today, new today, retention over the last 30 days, a streak, and a per-project forecast for the
next 7 days.
