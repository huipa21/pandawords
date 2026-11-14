# Architecture overview

## Containers (production, `deploy/compose.yml`)

```
               external Caddy (existing container, network ${CADDY_NETWORK})
                                │  reverse_proxy web:80
┌──────────────────────── pandawords (internal network) ─────────────────────────┐
│  web       nginx:alpine — serves the Vue SPA, proxies /api → api:8000,         │
│            serves media via X-Accel-Redirect (internal location)               │
│  api       pandawords-api image — uvicorn app.main:app                         │
│  worker    pandawords-api image — python -m app.worker                         │
│  migrate   pandawords-api image — python -m app.db.migrate (one-shot);         │
│            api and worker depend on it (service_completed_successfully)        │
│  surrealdb surrealdb/surrealdb:v3.3.x — rocksdb:/data/db                       │
└────────────────────────────────────────────────────────────────────────────────┘
volumes: surreal-data, media, lexicon (read-only, transferred separately), backups
```

Only `web` joins the Caddy network. SurrealDB is never exposed publicly.

## Local development

| Process | How it runs | Port |
|---|---|---|
| SurrealDB dev (persistent) | Podman, `deploy/compose.dev.yml` | 8100 |
| SurrealDB test (in-memory, throwaway) | Podman, same compose file | 8101 |
| API | `uv run uvicorn --reload` on the host | 8000 |
| Worker | `uv run python -m app.worker` on the host | — |
| Web | `pnpm dev` (Vite proxies `/api` → 8000) | 5173 |

## Request flow

1. The SPA calls `/api/...` with the access token from memory. On a 401 it calls `/api/auth/refresh`
   once (with the httpOnly refresh cookie), then retries.
2. Routers validate input and resolve `current_user`, then call services. Services call repositories
   in `app/db/`.
3. Slow work (lexicon materialization, enrichment, audio, LLM) is written as a `job` record. The
   worker wakes up via a LIVE query, with polling as a fallback. The UI polls the job status or
   refetches the data.

The API exposes `/api/healthz` for liveness, `/api/readyz` for readiness, and its schema at
`/api/openapi.json`. Readiness remains a stub until the database lifecycle is implemented.
Backend settings resolve `.env.dev` from the main worktree (or the project root outside Git);
inherited environment variables take precedence.

### Project API

Authenticated, enabled users who have completed the password change can use:

| Route | Contract |
|---|---|
| `POST /api/projects` | `ProjectCreate` → `201 ProjectRead` |
| `GET /api/projects?page=1&page_size=20` | `ProjectPage {items, total, page, page_size}` |
| `GET /api/projects/{id}` | `ProjectRead` |
| `PATCH /api/projects/{id}` | `ProjectUpdate` → `ProjectRead` |
| `DELETE /api/projects/{id}` | `204`, no body |

Project IDs use the strict opaque `rid` codec, not raw database IDs. Pagination follows the
existing admin API: page ≥ 1 (maximum 2,147,483,647), page size 1–100, default 20; newest
`created_at` first, with `id` as the stable tie-breaker. Counts and items are owner-scoped and
read in one transaction. Successful responses use `Cache-Control: no-store`.
Malformed/wrong-table IDs, missing projects and other users' projects all return the same
`404 project.not_found`, including for administrators. Input validation returns
`422 validation.invalid`. Contracts are generated in `frontend/src/api/{openapi.json,schema.d.ts}`.
Project tree and word-add endpoints are separate tasks; they must reuse the same project `rid`
and ownership contract rather than inventing scalar IDs.

### Scheduling service and settings

Authenticated `GET /api/projects/{id}/study-plan` returns `StudyPlanRead`, with bounded queue
pagination (`offset`, `limit`), plan settings, raw due/new and UTC completed counts, remaining
allowances, exam capacity/buffer warnings and actual seven-day forecasts.
`PUT /api/projects/{id}/study-plan/order` takes `SenseOrderUpdate` (every visible selected
sense ID once), preserves hidden slots and returns `SenseOrderRead` (full persisted order).
Other-owner projects return 404; success uses `Cache-Control: no-store`.
`GET /api/dashboard` returns only the authenticated owner's deduplicated due/new availability,
completed counts, nullable 30-date retention, streak and project forecasts. It cannot select
another owner. These routers call `services/study_plan.py`; pure UTC/FSRS calculations live
in `study_plan_calculations.py`, owner-bound snapshots/order writes in `db/study_plan.py`.
Settings continue to use complete `plan` replacement through the project PATCH endpoint.

`services/srs.py` owns per-user/sense FSRS 6.x cards and atomic completed reviews.
Add-to-project creates absent cards in the membership/job transaction. Legacy selections,
including hidden ones, are reconciled through `reconcile_memberships` before queue reads.
Cards/history survive project deletion. The exercise framework, not a correctness-bearing
client endpoint, supplies immutable graded attempts; confirmation applies the final rating,
card update and exactly-once receipt together with owner/tree/daily-limit checks.

Authenticated `GET/PATCH /api/auth/me/srs-preferences` uses `SrsPreferences`
(`desired_retention`, default 0.9, strictly between 0 and 1). It cannot select another user
and preserves other preferences. PATCH requires `SrsPreferencesUpdate.desired_retention`;
an empty body cannot silently reset a saved setting. Auth's public `UserPreferences` also exposes the setting.
The generated OpenAPI/types include this contract. Server timing defaults are configurable
with the four `SRS_{RECOGNITION,RECALL}_{FAST,SLOW}_MS` environment settings.

## Backend modules

### Optional LLM boundary

Only `services/llm.py` contacts DeepSeek through the approved OpenAI SDK JSON mode.
Forward migration `0014` adds `llm_cache` (owner/key) and `llm_budget` (owner/UTC day).
Caches survive process restarts and remain available without a provider key or with a zero
budget. Private inputs never share cache entries; shared generation derives inputs directly
from verified shared dictionary records. Prompt/schema/model/input changes invalidate keys.
Every dispatch reserves an attempt in a conflict-retried DB transaction **before** contacting
the provider, including retries. Failures consume reservations; cache hits do not.
SDK retries are disabled; application retries/timeouts and output tokens are bounded.
Logs contain only unavailable reason and attempt count, not prompts, responses or keys;
SDK payload-bearing debug events are filtered even when debug logging is enabled.

| Module | Responsibility |
|---|---|
| `app/main.py` | App factory, routers, lifespan (DB connect, admin bootstrap) |
| `app/core/` | config, security (JWT, hashing), errors, logging |
| `app/db/` | client, migrations, repositories, named queries, schema snapshot |
| `app/domain/` | pydantic models |
| `app/services/` | auth, projects, dictionary, enrichment, lexicon reader, srs, exercises, llm, media, jobs, bundles |
| `app/api/` | routers per resource |
| `app/worker/` | job loop + handlers registry |
| `scripts/` | lexicon download/build |

## Frontend modules

| Path | Responsibility |
|---|---|
| `src/app/` | main.ts, router, plugins (naive, i18n, pinia), AppShell |
| `src/design/` | tokens.ts, naive-theme.ts, uno preset, cytoscape styles |
| `src/components/` | shared domain components (see `docs/ui/components.md`) |
| `src/features/<x>/` | auth, projects, words, review, graph, reading, admin, settings, dev-design |
| `src/api/` | generated `schema.d.ts`, `client.ts` (auth + refresh middleware) |
| `src/stores/` | auth, preferences (theme, locale, accent) |
| `src/i18n/` | `zh-CN.json`, `en.json` |

## Routes (frontend)

`/review` is the authenticated global learning dashboard/project picker.
`/projects/:id/plan` provides progress, server-calculated exam pacing, seven-date forecasts,
the existing project settings form, an explicit visible-sense priority draft and separate
personal desired-retention settings. Both use generated contracts and the authenticated API
client; no learning data is persisted in browser storage. Feature-local display, form and
priority components live in `src/features/study/`.

`/login` · `/projects` · `/projects/:id` (tree) · `/projects/:id/review` · `/projects/:id/plan` ·
`/words` (all-words graph) · `/words/:lemmaId` · `/reading/:passageId` · `/settings` ·
`/admin/users` · `/admin/backup` · `/dev/design` (dev only)

## Media storage and delivery

`api/media.py` → `services/media.py` → `db/media.py` serves authenticated
`GET /api/media/{rid}` (canonical `encode_rid(record, "media")` token). Both the media
record and its current target must be shared or owned by the requester; absent,
inaccessible, unsafe and missing-file assets all return the same 404. Success has an
empty application body and `X-Accel-Redirect: /_media/<relative path>`, an allowlisted
content type, `nosniff` and `Cache-Control: private, no-store`.

Trusted audio/image producers use
`await media.store(db, settings, MediaCreate(...), content: bytes) -> MediaRead`.
Input includes an SDK `RecordID` target, optional owner subject, kind, MIME, source,
optional attribution and US/UK accent. Shared assets require a shared target.
`await media.read(db, settings, rid, owner) -> MediaRead` validates access and file
existence. Returned metadata includes opaque media/target IDs, kind, MIME, source,
attribution and accent, never storage paths. Producers can retain the media ID for
cache reuse; downloading, TTS, cache discovery and pronunciation linking are separate tasks.
Storage creates generated exclusive filenames below configured `media_dir`, rejects
links/traversal, and removes files when metadata persistence fails.
