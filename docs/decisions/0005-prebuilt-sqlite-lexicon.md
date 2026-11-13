# 0005 — Prebuilt read-only SQLite lexicon

**Status:** Accepted (2026-11-13)

**Context.** The full Wiktionary extract is several GB. The server has 4 GB RAM. Users only touch a
small fraction of words.

**Decision.** `backend/scripts` streams kaikki (Wiktionary), Open English WordNet, ECDICT and
wordfreq into `data/lexicon/lexicon.sqlite`, built on the laptop and transferred. At runtime it's
mounted read-only. Only words that users add are materialized into SurrealDB's shared dictionary.

**Consequences.** SurrealDB stays small and fast. The lexicon is versioned separately (`manifest.json`)
and isn't part of site backups. Rebuilding the lexicon never rewrites materialized rows automatically;
a refresh job can be added later.
