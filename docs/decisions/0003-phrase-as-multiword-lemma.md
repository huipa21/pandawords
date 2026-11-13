# 0003 — Phrases are multi-word lemmas

**Status:** Accepted (2026-11-13)

**Context.** Idioms have meanings that aren't the sum of their words, but users still want to see
which phrases a word appears in. Wiktionary already models idioms and phrasal verbs as entries with
their own POS and senses.

**Decision.** A phrase is a `lemma` with `kind = 'phrase'` and its own lexemes/senses. A
`contains {position}` edge links it to each component lexeme, always. `sense used_in phrase` exists
only when a word's sense applies literally.

**Consequences.** Phrases reuse the add flow, overrides, FSRS and exercises. "Phrases containing X" is
a reverse traversal of `contains`. Sentences and passages stay separate tables.
