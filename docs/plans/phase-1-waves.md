# Phase 1 wave map

Source of truth: the Phase 1 table in [PLAN.md](PLAN.md) (columns **Depends on** and **Wave**).
Task details: [phase-1.md](phase-1.md). Procedure: [../dev/workflow.md](../dev/workflow.md).
Status: PLAN.md. Current run, blockers, backlog, findings: [PROGRESS.md](PROGRESS.md). After an interruption, follow
[workflow.md - Resume after an interruption](../dev/workflow.md#resume-after-an-interruption).

## Instructions for the agent

- Run the waves in order. Tasks in the same wave don't depend on each other, so run them in parallel (one worktree per task).
- Before you start a task, check that every task in its `needs` list is ✅ in PLAN.md.
- When a task is merged, check the tasks in its `unlocks` list. Each one is ready once all of its own `needs` are ✅.
- Start with "implement task 1.1.1".

## Wave grid (each column is a wave)

| W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 | W10 | W11 | W12 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.1.1 | 1.1.2 | 1.1.3 | 1.2.3 | 1.3.3 | 1.3.4 | 1.5.1 | 1.5.2 | 1.5.3 | 1.5.4 | 1.5.6 | 1.6.6 |
|  | 1.1.4 | 1.2.2 | 1.3.2 | 1.4.4 | 1.3.5 | 1.6.5 |  |  | 1.5.5 | 1.6.1 |  |
|  | 1.2.1 | 1.3.1 | 1.4.3 | 1.6.3 | 1.6.4 |  |  |  | 1.6.2 |  |  |
|  | 1.4.1 | 1.4.2 | 1.4.5 |  |  |  |  |  |  |  |  |

## Flow by wave (task → tasks it unlocks in later waves)

```text
WAVE 1
  1.1.1  Initialize repository (main branch, ignore files, .env.example, README)
      needs:   —
      unlocks: 1.1.2 (W2), 1.1.4 (W2), 1.2.1 (W2), 1.4.1 (W2)

WAVE 2
  1.1.2  dev.ps1 skeleton: dispatch, root/env resolution, setup, fallback sources
      needs:   1.1.1 (W1)
      unlocks: 1.3.1 (W3)
  1.1.4  VS Code workspace settings and recommended extensions
      needs:   1.1.1 (W1)
      unlocks: — (end)
  1.2.1  Backend uv project (Python 3.14, ruff, basedpyright, pytest)
      needs:   1.1.1 (W1)
      unlocks: 1.1.3 (W3), 1.2.2 (W3), 1.3.2 (W4)
  1.4.1  Frontend project (pnpm workspace, Vite 8, Vue 3.5, TS 6.0, eslint, vitest)
      needs:   1.1.1 (W1)
      unlocks: 1.1.3 (W3), 1.4.2 (W3), 1.4.5 (W4)

WAVE 3
  1.1.3  lefthook pre-commit (ruff, eslint, secrets guard)
      needs:   1.2.1 (W2), 1.4.1 (W2)
      unlocks: — (end)
  1.2.2  API skeleton: app factory, settings, logging, error format, health
      needs:   1.2.1 (W2)
      unlocks: 1.2.3 (W4), 1.4.5 (W4), 1.6.3 (W5)
  1.3.1  Podman dev (8100) and test (8101) SurrealDB, reset-db
      needs:   1.1.2 (W2)
      unlocks: 1.2.3 (W4), 1.3.2 (W4)
  1.4.2  Design tokens + generators (CSS vars, Naive, Uno, Cytoscape) + fonts + enforcement
      needs:   1.4.1 (W2)
      unlocks: 1.4.3 (W4)

WAVE 4
  1.2.3  SurrealDB client lifecycle + readyz
      needs:   1.2.2 (W3), 1.3.1 (W3)
      unlocks: 1.3.3 (W5)
  1.3.2  SurrealQL 3.3 verification spike (N01–N23)
      needs:   1.3.1 (W3), 1.2.1 (W2)
      unlocks: 1.3.3 (W5), 1.6.4 (W6)
  1.4.3  App shell: router, Pinia, i18n, theme toggle, responsive layout, icons
      needs:   1.4.2 (W3)
      unlocks: 1.4.4 (W5), 1.5.5 (W10), 1.6.1 (W11), 1.6.3 (W5)
  1.4.5  OpenAPI → TS types pipeline (gen-api) + API client with refresh
      needs:   1.4.1 (W2), 1.2.2 (W3)
      unlocks: 1.5.5 (W10)

WAVE 5
  1.3.3  Migration runner (_migration, checksums, transactions, .py support)
      needs:   1.2.3 (W4), 1.3.2 (W4)
      unlocks: 1.3.4 (W6), 1.3.5 (W6), 1.6.1 (W11), 1.6.4 (W6)
  1.4.4  /dev/design preview page (dev only)
      needs:   1.4.3 (W4)
      unlocks: — (end)
  1.6.3  Dockerfiles (api, web/nginx)
      needs:   1.2.2 (W3), 1.4.3 (W4)
      unlocks: 1.6.4 (W6)

WAVE 6
  1.3.4  Schema snapshot + drift test
      needs:   1.3.3 (W5)
      unlocks: 1.5.1 (W7), 1.6.2 (W10)
  1.3.5  Test harness: per-session test DB, fresh_db, ASGI client
      needs:   1.3.3 (W5)
      unlocks: 1.5.1 (W7), 1.6.2 (W10)
  1.6.4  Production compose.yml + pre-migrate export + Caddy snippet
      needs:   1.6.3 (W5), 1.3.3 (W5), 1.3.2 (W4)
      unlocks: 1.6.2 (W10), 1.6.5 (W7)

WAVE 7
  1.5.1  Migration: user, refresh_token
      needs:   1.3.4 (W6), 1.3.5 (W6)
      unlocks: 1.5.2 (W8)
  1.6.5  dev.ps1 release (images → tar.gz, deploy bundle)
      needs:   1.6.4 (W6)
      unlocks: — (end)

WAVE 8
  1.5.2  Security core: argon2, JWT, refresh rotation, admin bootstrap
      needs:   1.5.1 (W7)
      unlocks: 1.5.3 (W9)

WAVE 9
  1.5.3  Auth API (login, refresh, logout, me, password) + forced change gate
      needs:   1.5.2 (W8)
      unlocks: 1.5.4 (W10), 1.5.5 (W10), 1.6.2 (W10)

WAVE 10
  1.5.4  Admin users API
      needs:   1.5.3 (W9)
      unlocks: 1.5.6 (W11)
  1.5.5  Frontend auth: login, store, guards, change password
      needs:   1.5.3 (W9), 1.4.3 (W4), 1.4.5 (W4)
      unlocks: 1.5.6 (W11)
  1.6.2  Worker skeleton + job table + jobs API
      needs:   1.3.4 (W6), 1.3.5 (W6), 1.5.3 (W9), 1.6.4 (W6)
      unlocks: 1.6.1 (W11)

WAVE 11
  1.5.6  Frontend admin users page
      needs:   1.5.4 (W10), 1.5.5 (W10)
      unlocks: 1.6.6 (W12)
  1.6.1  dev.ps1 up/down/check/test complete
      needs:   1.3.3 (W5), 1.4.3 (W4), 1.6.2 (W10)
      unlocks: 1.6.6 (W12)

WAVE 12
  1.6.6  E2E: admin creates user → first login → forced password change
      needs:   1.5.6 (W11), 1.6.1 (W11)
      unlocks: — (end)

```

## Edge list (dependency ──► dependent)

```text
W1 1.1.1  ──►  W2 1.1.2
W1 1.1.1  ──►  W2 1.1.4
W1 1.1.1  ──►  W2 1.2.1
W1 1.1.1  ──►  W2 1.4.1
W2 1.2.1  ──►  W3 1.1.3
W2 1.4.1  ──►  W3 1.1.3
W2 1.2.1  ──►  W3 1.2.2
W2 1.1.2  ──►  W3 1.3.1
W2 1.4.1  ──►  W3 1.4.2
W3 1.2.2  ──►  W4 1.2.3
W3 1.3.1  ──►  W4 1.2.3
W3 1.3.1  ──►  W4 1.3.2
W2 1.2.1  ──►  W4 1.3.2
W3 1.4.2  ──►  W4 1.4.3
W2 1.4.1  ──►  W4 1.4.5
W3 1.2.2  ──►  W4 1.4.5
W4 1.2.3  ──►  W5 1.3.3
W4 1.3.2  ──►  W5 1.3.3
W4 1.4.3  ──►  W5 1.4.4
W3 1.2.2  ──►  W5 1.6.3
W4 1.4.3  ──►  W5 1.6.3
W5 1.3.3  ──►  W6 1.3.4
W5 1.3.3  ──►  W6 1.3.5
W5 1.6.3  ──►  W6 1.6.4
W5 1.3.3  ──►  W6 1.6.4
W4 1.3.2  ──►  W6 1.6.4
W6 1.3.4  ──►  W7 1.5.1
W6 1.3.5  ──►  W7 1.5.1
W6 1.6.4  ──►  W7 1.6.5
W7 1.5.1  ──►  W8 1.5.2
W8 1.5.2  ──►  W9 1.5.3
W9 1.5.3  ──►  W10 1.5.4
W9 1.5.3  ──►  W10 1.5.5
W4 1.4.3  ──►  W10 1.5.5
W4 1.4.5  ──►  W10 1.5.5
W6 1.3.4  ──►  W10 1.6.2
W6 1.3.5  ──►  W10 1.6.2
W9 1.5.3  ──►  W10 1.6.2
W6 1.6.4  ──►  W10 1.6.2
W10 1.5.4  ──►  W11 1.5.6
W10 1.5.5  ──►  W11 1.5.6
W5 1.3.3  ──►  W11 1.6.1
W4 1.4.3  ──►  W11 1.6.1
W10 1.6.2  ──►  W11 1.6.1
W11 1.5.6  ──►  W12 1.6.6
W11 1.6.1  ──►  W12 1.6.6
```
