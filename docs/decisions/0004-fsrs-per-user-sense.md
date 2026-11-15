# 0004 — FSRS card per (user, sense), auto-rating

**Status:** Accepted (2026-11-13)

**Context.** Spaced repetition is the core of the review plan. A word has several senses that are
learned separately. The same sense can be in several projects.

**Decision.** Use py-fsrs 6.x. There is one `memory:[user, sense]` card, shared across projects.
Ratings are derived automatically from correctness, response time and hint use (recognition
exercises are capped at Good), and the user can change the rating before continuing. Every answer is
logged in `review_log` with both the auto and the final rating.

**Consequences.** One forgetting curve per meaning. The logs support per-user FSRS parameter
optimization. Project queues are filtered views over the same cards.

**2026-11-15 extension (7.1.5).** Use the supported optimizer in the locked py-fsrs 6.3.3,
not a second optimization implementation. Its published optimizer extra requires PyTorch,
NumPy, pandas and tqdm, so it remains an explicit image/development opt-in rather than
burdening default installs. Isolated, bounded training and last-good/default fallback preserve
ordinary reviews without that extra or any external provider. See
[learning-engine.md](../architecture/learning-engine.md#per-user-fsrs-optimization-715)
for eligibility, metadata and future-only scheduling.
