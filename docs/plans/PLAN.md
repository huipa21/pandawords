# Master plan

Trigger work with **"implement task X.Y.Z"**. An epic (`X.Y`), a wave (`phase N wave W`) or a list
also works. Procedure: [../dev/workflow.md](../dev/workflow.md). Task details and acceptance criteria
are in `phase-N.md`. If a phase file doesn't exist yet, the agent asks before writing it.

**Legend.**
- Status: ⬜ todo · 🟡 in progress · ✅ done · ⛔ blocked
- Size: S ≈ < 1 h, M ≈ 1–3 h, L ≈ > 3 h of agent work
- **Wave**: tasks in the same wave of a phase have no dependencies on each other and can run in
  parallel once the earlier waves are done. A cross-phase dependency doesn't stop a task from
  starting early when it's already satisfied.
- Only the main agent edits this file, on `main`: 🟡 when a task starts, ✅ after merging.
- Status only. Current run, blockers with reasons, discovered backlog and findings go in
  [PROGRESS.md](PROGRESS.md). To resume after an interruption, see
  [../dev/workflow.md](../dev/workflow.md#resume-after-an-interruption).

## Phase 1 — Foundation ([details](phase-1.md) · [wave map](phase-1-waves.md))

| ID | Task | Depends on | Wave | Size | Status |
|---|---|---|---|---|---|
| 1.1.1 | Initialize repository (main branch, ignore files, `.env.example`, README) | — | 1 | S | ✅ |
| 1.1.2 | `dev.ps1` skeleton: dispatch, root/env resolution, `setup`, fallback sources | 1.1.1 | 2 | M | ✅ |
| 1.1.3 | lefthook pre-commit (ruff, eslint, secrets guard) | 1.2.1, 1.4.1 | 3 | S | ✅ |
| 1.1.4 | VS Code workspace settings and recommended extensions | 1.1.1 | 2 | S | ✅ |
| 1.2.1 | Backend uv project (Python 3.14, ruff, basedpyright, pytest) | 1.1.1 | 2 | S | ✅ |
| 1.2.2 | API skeleton: app factory, settings, logging, error format, health | 1.2.1 | 3 | M | ✅ |
| 1.2.3 | SurrealDB client lifecycle + `readyz` | 1.2.2, 1.3.1 | 4 | S | ✅ |
| 1.3.1 | Podman dev (8100) and test (8101) SurrealDB, `reset-db` | 1.1.2 | 3 | S | ✅ |
| 1.3.2 | SurrealQL 3.3 verification spike (N01–N23) | 1.3.1, 1.2.1 | 4 | M | ✅ |
| 1.3.3 | Migration runner (`_migration`, checksums, transactions, `.py` support) | 1.2.3, 1.3.2 | 5 | M | ✅ |
| 1.3.4 | Schema snapshot + drift test | 1.3.3 | 6 | S | ✅ |
| 1.3.5 | Test harness: per-session test DB, `fresh_db`, ASGI client | 1.3.3 | 6 | M | ✅ |
| 1.4.1 | Frontend project (pnpm workspace, Vite 8, Vue 3.5, TS 6.0, eslint, vitest) | 1.1.1 | 2 | S | ✅ |
| 1.4.2 | Design tokens + generators (CSS vars, Naive, Uno, Cytoscape) + fonts + enforcement | 1.4.1 | 3 | M | ✅ |
| 1.4.3 | App shell: router, Pinia, i18n, theme toggle, responsive layout, icons | 1.4.2 | 4 | M | ✅ |
| 1.4.4 | `/dev/design` preview page (dev only) | 1.4.3 | 5 | S | ✅ |
| 1.4.5 | OpenAPI → TS types pipeline (`gen-api`) + API client with refresh | 1.4.1, 1.2.2 | 4 | M | ✅ |
| 1.5.1 | Migration: `user`, `refresh_token` | 1.3.4, 1.3.5 | 7 | S | ✅ |
| 1.5.2 | Security core: argon2, JWT, refresh rotation, admin bootstrap | 1.5.1 | 8 | M | ✅ |
| 1.5.3 | Auth API (login, refresh, logout, me, password) + forced change gate | 1.5.2 | 9 | M | ✅ |
| 1.5.4 | Admin users API | 1.5.3 | 10 | S | ✅ |
| 1.5.5 | Frontend auth: login, store, guards, change password | 1.5.3, 1.4.3, 1.4.5 | 10 | M | ✅ |
| 1.5.6 | Frontend admin users page | 1.5.4, 1.5.5 | 11 | M | ✅ |
| 1.6.1 | `dev.ps1` `up`/`down`/`check`/`test` complete | 1.3.3, 1.4.3, 1.6.2 | 11 | M | ✅ |
| 1.6.2 | Worker skeleton + `job` table + jobs API | 1.3.4, 1.3.5, 1.5.3, 1.6.4 | 10 | M | ✅ |
| 1.6.3 | Dockerfiles (api, web/nginx) | 1.2.2, 1.4.3 | 5 | M | ✅ |
| 1.6.4 | Production `compose.yml` + pre-migrate export + Caddy snippet | 1.6.3, 1.3.3, 1.3.2 | 6 | M | ✅ |
| 1.6.5 | `dev.ps1 release` (images → tar.gz, deploy bundle) | 1.6.4 | 7 | S | ✅ |
| 1.6.6 | E2E: admin creates user → first login → forced password change | 1.5.6, 1.6.1 | 12 | S | ✅ |

## Phase 2 — Dictionary & projects ([details](phase-2.md))

| ID | Task | Depends on | Wave | Size | Status |
|---|---|---|---|---|---|
| 2.1.1 | Lexicon download scripts (kaikki, OEWN, ECDICT) + manifest | 1.2.1 | 1 | S | ✅ |
| 2.1.2 | Build `lexicon.sqlite` core from kaikki (lemma/lexeme/sense/pron/forms/audio/form_index) | 2.1.1 | 2 | L | ✅ |
| 2.1.3 | Merge ECDICT + wordfreq (zh gloss, exam tags, frequency, `common`) | 2.1.2 | 3 | M | ✅ |
| 2.1.4 | Align OEWN relations to senses | 2.1.2 | 3 | M | ✅ |
| 2.1.5 | Fixture lexicon (~50 words) + `LexiconReader` service | 2.1.3, 2.1.4 | 4 | M | ✅ |
| 2.1.6 | `dev.ps1 lexicon` + lexicon release artifact | 2.1.3, 2.1.4, 1.6.5 | 4 | S | ✅ |
| 2.2.1 | Migrations: dictionary tables and edges | 1.3.4, 1.3.5 | 1 | M | ✅ |
| 2.2.2 | ID helpers: deterministic keys, `rid` encode/decode | 1.2.3 | 1 | S | ✅ |
| 2.2.3 | Dictionary repository: idempotent materialize, effective reads, owner filter | 2.2.1, 2.2.2, 2.1.5 | 5 | M | ✅ |
| 2.3.1 | Migrations: `project`, `includes`, `override`, `note` | 2.2.1, 1.5.1 | 2 | S | ✅ |
| 2.3.2 | Project CRUD API + isolation tests | 2.3.1, 1.5.3, 2.2.2 | 3 | M | ✅ |
| 2.3.3 | Overrides, custom senses, notes API | 2.3.1, 2.2.3 | 6 | M | ✅ |
| 2.3.4 | Project tree query + API (includes/hidden + overrides) | 2.3.2, 2.3.3 | 7 | M | ✅ |
| 2.4.1 | Lemmatize (spaCy + form_index) + candidates API | 2.1.5, 2.2.2, 1.5.3 | 5 | M | ✅ |
| 2.4.2 | Add-to-project API: materialize, includes, enqueue jobs | 2.4.1, 2.2.3, 2.3.2, 1.6.2 | 6 | M | ✅ |
| 2.4.3 | `enrich` job: relations among materialized items, tags, frequency | 2.4.2 | 7 | M | ✅ |
| 2.5.1 | Media storage + authenticated serving (X-Accel-Redirect) | 2.2.1, 1.6.3 | 2 | M | ✅ |
| 2.5.2 | `audio` job: Wiktionary → edge-tts fallback (US/UK) | 2.5.1, 2.4.2 | 7 | M | ✅ |
| 2.6.1 | Word components + previews | 1.4.4, 1.4.5 | 1 | M | ✅ |
| 2.6.2 | Projects list/create/edit pages | 2.3.2, 1.5.5 | 4 | M | ✅ |
| 2.6.3 | Add-word dialog (SenseSelectList, JobStatus) | 2.4.2, 2.6.1, 2.6.2 | 7 | M | ✅ |
| 2.6.4 | Project tree view (LemmaTree, hide/unhide with undo) | 2.3.4, 2.6.1, 2.6.2 | 8 | M | ✅ |
| 2.6.5 | Lemma detail page (overrides, notes, audio) | 2.3.3, 2.5.2, 2.6.1 | 8 | M | ✅ |
| 2.6.6 | E2E: project → add word → edit sense → hide sense | 2.6.3, 2.6.4, 2.6.5 | 9 | S | ✅ |

## Phase 3 — Learning engine ([details](phase-3.md))

| ID | Task | Depends on | Wave | Size | Status |
|---|---|---|---|---|---|
| 3.1.1 | Migrations: `memory`, `review_log` | 2.3.1 | 1 | S | ✅ |
| 3.1.2 | SRS service: FSRS wrapper, card creation on add, review apply, auto-rating | 3.1.1, 2.4.2 | 2 | M | ✅ |
| 3.1.3 | Daily plan, exam-date pacing, queue builder + plan API | 3.1.2 | 3 | M | ✅ |
| 3.2.1 | Exercise framework: registry, generate/grade API, server-side timing | 3.1.2 | 3 | M | ✅ |
| 3.2.2 | Distractor service (tags, morph groups, confusables, frequency band) | 3.2.1, 2.4.3 | 4 | M | ✅ |
| 3.2.3 | Exercises: `def2word`, `word2def`, `relation` | 3.2.2 | 5 | M | ✅ |
| 3.2.4 | Exercises: `cloze`, `listen` | 3.2.1, 2.5.2 | 4 | M | ✅ |
| 3.2.5 | DeepSeek client (JSON mode, caching, budget, fallback) | 1.2.2, 1.5.1 | 1 | S | ✅ |
| 3.2.6 | Exercise: `scenario` (cached generation) | 3.2.5, 3.2.1 | 4 | M | ✅ |
| 3.3.1 | Exercise components (ExerciseShell, ChoiceGrid, TypedAnswerInput, RatingBar, ReviewProgress) | 2.6.1, 3.2.1 | 4 | M | ✅ |
| 3.3.2 | Review session page | 3.3.1, 3.1.3, 3.2.3, 3.2.4 | 6 | M | ✅ |
| 3.3.3 | Plan settings + dashboard | 3.1.3, 2.6.2 | 4 | M | ✅ |
| 3.3.4 | E2E: review session | 3.3.2, 3.3.3 | 7 | S | ✅ |

## Phase 4 — Context & graph

| ID | Task | Depends on | Wave | Size | Status |
|---|---|---|---|---|---|
| 4.1.1 | Phrases: multi-word lemmas in lexicon + `contains` materialization | 2.2.3, 2.1.2 | 1 | M | ✅ |
| 4.1.2 | Phrase add flow + "phrases containing this word" (API + UI) | 4.1.1, 2.6.5 | 2 | M | ✅ |
| 4.2.1 | Migrations: `sentence`, `passage`, `used_in`, `part_of` | 2.2.1 | 1 | S | ✅ |
| 4.2.2 | Sentence/passage CRUD + ingestion (split, lemmatize, link senses, optional LLM) | 4.2.1, 2.4.1, 3.2.5 | 2 | L | ✅ |
| 4.2.3 | Reading view (highlight project words, add unknown words inline) | 4.2.2, 2.6.3 | 3 | M | 🟡 |
| 4.3.1 | Tags: hierarchical `member_of`, user tag CRUD, assignment UI | 2.2.1, 2.6.5 | 1 | M | ✅ |
| 4.3.2 | Morphemes from etymology templates (+ LLM fallback), morph groups | 2.1.2, 4.3.1, 3.2.5 | 2 | M | 🟡 |
| 4.4.1 | Graph API: subgraph by focus/depth/filters, node cap | 2.3.4, 4.1.1, 4.2.1, 4.3.1 | 2 | M | ✅ |
| 4.4.2 | GraphCanvas, legend, toolbar, all-words page, tree/graph toggle | 4.4.1, 2.6.4 | 3 | L | 🟡 |
| 4.4.3 | Relation editing (user `relates_to` create/delete) | 4.4.2 | 4 | S | 🟡 |
| 4.4.4 | Exercises use context: cloze from user sentences, tag/morph distractors | 4.2.2, 4.3.2, 3.2.3, 3.2.4 | 3 | M | 🟡 |

## Phase 5 — Dual coding & mnemonics

| ID | Task | Depends on | Wave | Size | Status |
|---|---|---|---|---|---|
| 5.1.1 | Image upload + Pixabay search/download, attach to sense | 2.5.1, 2.6.5 | 1 | M | ✅ |
| 5.1.2 | Mnemonic notes UI + DeepSeek suggestions | 3.2.5, 2.6.5 | 1 | S | ✅ |
| 5.1.3 | `image2word` exercise + media preferences in review | 5.1.1, 3.3.2 | 2 | M | 🟡 |

## Phase 6 — Import/export & backups

| ID | Task | Depends on | Wave | Size | Status |
|---|---|---|---|---|---|
| 6.1.1 | Bundle format, JSON Schema, serializers | 3.1.1, 4.2.1, 4.3.1, 5.1.1 | 1 | M | ⬜ |
| 6.1.2 | Project export (including progress and media) | 6.1.1 | 2 | M | ⬜ |
| 6.1.3 | Project import (merge by ID, remap user-owned, progress option) | 6.1.2 | 3 | L | ⬜ |
| 6.1.4 | User full backup/restore | 6.1.3 | 4 | M | ⬜ |
| 6.1.5 | Admin site backup/restore, scheduled `backup` service, `restore.sh` | 1.6.4 | 1 | M | ⬜ |
| 6.1.6 | UI for export, import and backup | 6.1.2, 6.1.3, 6.1.4, 6.1.5 | 5 | M | ⬜ |

## Phase 7 — PWA & hardening

| ID | Task | Depends on | Wave | Size | Status |
|---|---|---|---|---|---|
| 7.1.1 | PWA: manifest, icons, service worker precache, install prompt | 1.4.3 | 1 | S | ⬜ |
| 7.1.2 | Offline review queue (prefetch due cards, sync answers) | 7.1.1, 3.3.2 | 2 | L | ⬜ |
| 7.1.3 | Security hardening: rate limits, nginx headers/CSP, ownership audit | 1.5.4, 1.6.4 | 1 | M | ⬜ |
| 7.1.4 | Performance pass: graph queries, indexes, bundle size | 4.4.2 | 1 | M | ⬜ |
| 7.1.5 | Per-user FSRS parameter optimization from review logs | 3.1.2 | 1 | M | ⬜ |
