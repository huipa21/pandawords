# Decision records

Short and immutable. If a decision changes, add a new ADR that supersedes the old one and update the
old one's status line only.

| # | Decision | Status |
|---|---|---|
| [0001](0001-surrealdb-3-3.md) | SurrealDB 3.3.x now, 4.x later | Accepted |
| [0002](0002-shared-dictionary-user-overlay.md) | Shared dictionary + per-user overlay | Accepted |
| [0003](0003-phrase-as-multiword-lemma.md) | Phrases are multi-word lemmas with `contains` edges | Accepted |
| [0004](0004-fsrs-per-user-sense.md) | FSRS card per (user, sense), auto-rating | Accepted |
| [0005](0005-prebuilt-sqlite-lexicon.md) | Prebuilt read-only SQLite lexicon, lazy materialization | Accepted |
| [0006](0006-backend-owned-auth.md) | Auth and authorization in FastAPI, not SurrealDB permissions | Accepted |
| [0007](0007-deepseek-optional-llm.md) | DeepSeek as the only, optional LLM | Accepted |
| [0008](0008-frontend-stack.md) | Vue 3.5 + TS 6.0 + Naive UI + UnoCSS + Lucide + Cytoscape | Accepted |
| [0009](0009-local-build-manual-deploy.md) | No CI; local Podman build, manual transfer | Accepted |
| [0010](0010-forward-only-migrations.md) | Forward-only `.surql` migrations, one-shot migrate service | Accepted |
| [0011](0011-design-tokens-single-source.md) | Design tokens in one TS file, enforced by lint | Accepted |
| [0012](0012-worktree-parallel-agents.md) | Numbered plan, worktree per task, parallel agents | Accepted |
