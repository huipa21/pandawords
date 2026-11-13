# AGENTS.md — PandaWords

Multi-user English vocabulary app (learner's source language: Chinese). Words form a personal
knowledge graph (lemma → lexeme → sense, phrases, sentences, passages, morphemes, tags) and are
learned with FSRS spaced repetition and graph-aware exercises.

Read this file first. Load other docs **only when the task needs them** — see [docs/README.md](docs/README.md).

## Stack (pinned)

| Layer | Choice |
|---|---|
| Backend | Python **3.14**, uv, FastAPI, pydantic v2, `surrealdb` SDK 3.0 (async, WebSocket) |
| DB | SurrealDB **3.3.x** (RocksDB), Podman locally, Docker on server |
| Worker | Same image as API, `python -m app.worker`, job table + LIVE wakeup |
| Frontend | Node **24 LTS**, pnpm, Vue 3.5, Vite 8, TypeScript **6.0** (not 7), Pinia, Vue Router, Naive UI, UnoCSS, Lucide icons, Cytoscape.js |
| LLM | DeepSeek (OpenAI-compatible), optional — every feature must work without it |

## Repo map

```
backend/app/{api,core,db,domain,services,worker}   backend/app/db/{migrations,queries}
backend/scripts/        lexicon build & one-off tools     backend/tests/
frontend/src/{app,design,components,features,api,stores,i18n}
deploy/                 compose.yml (prod), compose.dev.yml (Podman dev/test DB), nginx, Caddy snippet
scripts/dev.ps1         all dev commands                   data/  (gitignored: lexicon, media)
docs/                   product, architecture, ui, dev, decisions (ADRs), plans
```

## Commands (PowerShell 7)

| Command | Purpose |
|---|---|
| `./scripts/dev.ps1 setup` | Check tools, install Python 3.14 via uv, `uv sync`, `pnpm install`, create `.env.dev` |
| `./scripts/dev.ps1 up` / `down` | Start/stop dev DB (8100) + migrate + seed + API (8000) + worker + Vite (5173) |
| `./scripts/dev.ps1 check` | Lint + format check + type check (backend & frontend) — quiet output |
| `./scripts/dev.ps1 test [-Backend\|-Frontend\|-E2E]` | Tests against throwaway DB (8101) |
| `./scripts/dev.ps1 reset-db` | Wipe dev database |
| `./scripts/dev.ps1 lexicon` | Download + build lexicon SQLite files into `data/lexicon/` |
| `./scripts/dev.ps1 gen-api` | Regenerate frontend API types from OpenAPI |
| `./scripts/dev.ps1 release -Version x.y.z` | Build linux/amd64 images, save to `dist/*.tar.gz` |

(Commands are created in Phase 1; until a command exists, see [docs/plans/PLAN.md](docs/plans/PLAN.md).)

## Task workflow (default behavior)

The user triggers work with **"implement task X.Y.Z"** (or an epic `X.Y`, a wave, or a list).
Full procedure: [docs/dev/workflow.md](docs/dev/workflow.md). Summary:

1. Read the task row in [PLAN.md](docs/plans/PLAN.md) and its detail in `docs/plans/phase-N.md`.
   Stop and report if any dependency is not ✅.
2. **Parallel by default**: split requested work into independent tasks/subtasks (no dependency
   between them, disjoint files) and run them with **parallel sub-agents**, one git worktree each.
   Do sequential work directly.
3. Per task: branch `task/X.Y.Z-slug` + worktree `../pandawords.worktrees/X.Y.Z`; implement;
   `dev.ps1 check` and relevant tests pass; update directly-related docs; commit.
4. Merge each branch into `main` (`--no-ff`) one at a time, re-run `check` after each merge.
5. Clean up: `git worktree remove`, `git branch -d`, and confirm the folder is gone.
6. Only the main agent edits [PLAN.md](docs/plans/PLAN.md) (status: 🟡 + commit before starting,
   ✅ after merging) and [PROGRESS.md](docs/plans/PROGRESS.md) (current run, blockers, backlog,
   findings log), both on `main`. On "resume", read PROGRESS.md first, then follow
   [workflow.md § Resume](docs/dev/workflow.md#resume-after-an-interruption). Report results.

## Hard rules

1. SurrealQL lives **only** in `backend/app/db/`. Always bind parameters (`$name`); never format strings into queries.
2. Every query touching user data filters by owner (`owner = $user` or `owner = NONE` for shared dictionary rows). Add a cross-user isolation test for each new user-data endpoint.
3. Migrations are forward-only and **immutable once merged**. Schema change = new file + regenerated `schema.snapshot.json`.
4. Don't trust memory for SurrealDB 3.x syntax. Verify against the dev DB and record findings in [docs/dev/surrealdb-notes.md](docs/dev/surrealdb-notes.md).
5. UI: Naive UI + UnoCSS + Lucide only. No raw colors/px/font sizes in components — use design tokens ([docs/ui/tokens.md](docs/ui/tokens.md)). Reuse domain components ([docs/ui/components.md](docs/ui/components.md)).
6. No hard-coded UI text: vue-i18n keys in both `zh-CN` and `en`.
7. Never hand-write API types; run `gen-api` after backend schema changes.
8. Secrets only in `.env.dev` / server `.env` (gitignored). Commit `.env.example` changes.
9. Keep modules under ~300 lines; one responsibility per file.
10. Significant new dependency or design change → add an ADR in `docs/decisions/`.
11. Updating docs as part of a task is expected. **Creating new documents or starting a new Q&A/design round requires asking the user first.**
12. No CI service: all checks run locally via `dev.ps1` and lefthook. Deployment = local image build → manual transfer ([docs/dev/deployment.md](docs/dev/deployment.md)).

## Definition of done

Code + focused tests pass · `check` clean · related docs/ADRs updated · merged to `main` ·
worktree and branch removed · PLAN.md status ✅.
