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

## Backend modules

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
