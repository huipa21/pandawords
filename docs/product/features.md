# Features by phase

Task-level breakdown and status: [../plans/PLAN.md](../plans/PLAN.md).

## Phase 1 — Foundation
- Monorepo, tooling, lefthook, `dev.ps1`
- Podman dev/test SurrealDB, migration runner, schema snapshot
- FastAPI skeleton, worker skeleton, design tokens, app shell (light/dark, zh-CN/en, responsive)
- Auth: admin bootstrap, admin-created users, forced password change
- Release packaging (images → tar.gz) and production compose

## Phase 2 — Dictionary & projects (MVP core)
- Lexicon build: Wiktionary (kaikki), Open English WordNet, ECDICT, wordfreq
- Add word: lemmatize → choose senses (common ones pre-checked) → add to project
- Background enrichment: relations to words already in the user's graph
- US/UK pronunciation: Wiktionary audio, with edge-tts as fallback
- Project tree, hide/unhide per project, per-user overrides, notes

## Phase 3 — Learning engine
- FSRS per (user, sense); auto-rating from correctness and response time, which the user can change
- Exercises: def→word, word→def, relation quiz, cloze, listen→spell, scenario→word (DeepSeek)
- Daily new-word limit, review queue, optional exam-date pacing, dashboard

## Phase 4 — Context & graph
- Phrases as multi-word lemmas, with "phrases containing this word"
- Sentences and passages: ingestion, linking words to senses, reading view
- Tags (hierarchical), morphemes and morph groups
- All-words graph explorer, relation editing

## Phase 5 — Dual coding & mnemonics
- Image upload and Pixabay search, mnemonic notes and suggestions, image→word exercise

## Phase 6 — Import/export & backups
- Project bundle export/import (including progress), user full backup/restore, admin site backup `.tar.gz`

## Phase 7 — PWA & hardening
- Installable PWA, offline review queue, rate limiting, security headers, performance pass
