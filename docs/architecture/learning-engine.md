# Learning engine

## Unit of memory

One FSRS card per **(user, sense)**, stored as `memory:[user, sense]`. A phrase's senses are cards
too. A sense included in several projects shares one card. Reviewing it from any project updates
the same memory.

## Scheduling (py-fsrs 6.x)

- `Scheduler` with default parameters at first. Per-user parameter optimization (from `review_log`)
  comes later.
- Desired retention: per-user setting, default 0.9.
- A new card is created when a sense is first added. It becomes reviewable once it is introduced
  through the daily plan.

## Auto-rating (the user can change the rating before moving on)

Exercises are either **recognition** (choose from options) or **recall** (type or produce).

| Outcome | Recognition | Recall |
|---|---|---|
| Wrong / gave up | Again | Again |
| Correct but slow (> slow threshold) or used a hint | Hard | Hard |
| Correct, normal time | Good | Good |
| Correct and fast (< fast threshold) | Good (capped) | Easy |

- The thresholds are per exercise type and per user: the rolling median of their correct response
  times × 0.6 (fast) / × 1.8 (slow). Until 20 samples exist, use defaults from settings.
- Response time is measured on the client from when the prompt is shown to when the answer is
  submitted. It is capped at 60 s.
- `review_log` stores `auto_rating`, the final `rating` and `duration_ms`.

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

## Daily plan (per project)

- `plan.daily_new`: the maximum number of new senses introduced per day.
- `plan.exam_date` (optional): suggested daily new = ceil(remaining new ÷ max(1, days left − 7)),
  capped by `daily_new`. The UI shows when the plan can't finish before the exam.
- `plan.review_cap` (optional): the maximum number of reviews per day. Overdue cards are ordered by
  retrievability (lowest first).
- Queue order: due reviews first, then new senses in project order (the user can reorder).

## Dashboard

Due today, new today, retention over the last 30 days, a streak, and a per-project forecast for the
next 7 days.
