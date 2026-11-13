# 0004 — FSRS card per (user, sense), auto-rating

**Status:** Accepted (2026-11-13)

**Context.** Spaced repetition is the core of the review plan. A word has several senses that are
learned separately. The same sense can be in several projects.

**Decision.** Use py-fsrs 6.x. There is one `memory:[user, sense]` card, shared across projects.
Ratings are derived automatically from correctness, response time and hint use (recognition
exercises are capped at Good), and the user can change the rating before continuing. Every answer is
logged in `review_log` with both the auto and the final rating.

**Consequences.** One forgetting curve per meaning. The logs allow per-user FSRS parameter
optimization later. Project queues are filtered views over the same cards.
