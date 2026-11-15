# Architecture overview

## Personal relation editing (4.4.3)

Authenticated `POST /api/relations` accepts `{start, end, type}` with opaque sense
IDs. It returns `{relation, created}`: 201 for a new personal link, 200 with
`created: false` for an identical retry/duplicate. Owner/ID/source injection and
unsupported types are rejected; self-links return 422 `relation.self_link`.
`GET /api/relations?sense_id=...&page=1&page_size=20` lists incoming/outgoing
visible shared/personal links with effective endpoint labels and edge-level `readonly`.
Pages are at most 100 records. `DELETE /api/relations/{id}` removes only a currently
visible requester-owned edge (204); missing, shared, foreign or inaccessible links
return 404. Identity collisions return 409. Successful reads/creates are no-store.
Router → service → repository preserves the existing domain-error boundary.

`GET /api/graph/seeds` also accepts repeated `node_types` filters, applied before
effective-label matching and pagination. The relation editor requests only senses,
never a full graph. Graph/detail panels share `SenseRelations`; successful graph edits
reload the same bounded neighborhood while preserving its selected sense.

## Graph presentation and discovery (4.4.2)

`GET /api/graph/seeds?q=&page=1&page_size=20&project_id=` is authenticated,
no-store and returns generated discriminated effective graph nodes, not a graph snapshot.
It shares the graph authorization snapshot: the non-hidden per-project union plus owned
records globally, or only one owner-checked project's visible selections when scoped.
Effective overridden labels are matched case-insensitively before pagination. Authorization
and batch sizes retain existing graph safety bounds; oversized authorization fails explicitly.
The frontend checks node labels, identities, edge endpoints and the 300-node cap before
rendering. `/words` and project graph mode share `GraphExplorer`; Cytoscape/fcose/dagre are
presentation-only and never infer authorization or relations. Focus expansion replaces the
bounded neighborhood; neither initial discovery nor layout changes fetch a full graph.

## Private image flow (5.1.1)

`/api/images/senses/{sense_id}` provides authenticated list/raw upload and
`/{image_id}` removal. Upload bodies are encoded image bytes, not multipart; send their actual
MIME and a stable `request-id` header (16–80 alphanumeric, `_` or `-` characters).
The streaming API rejects content above 10 MiB before decoding all frames with Pillow.
Stored media IDs use the existing protected `/api/media/{rid}` endpoint and local media store.

Pixabay is optional and explicit: `/api/images/pixabay/search?q=...` returns owner-cached
result identities and attribution, not remote image URLs. Selecting an identity at
`/api/images/senses/{sense_id}/pixabay` enqueues an owner-bound `image` job; the UI polls the
existing job API, then reloads local attachments. The worker rechecks target/cache ownership
and HTTPS provider hosts on every redirect, bounds streamed responses and decode work, and
preserves creator/source-page/Content License attribution. Terminal errors are public-safe;
resubmitting the same selection retries a failed job without duplicating an attachment.

## Optional image review (5.1.3)

Production `image2word` is local recall over a stable, byte-validated, owner-only exact-sense
attachment. Public prompts contain protected IDs and only answer-safe required credit; images
whose credit leaks a selected form are unavailable. Review renders these IDs through
`ProtectedImage`, not the audio player. Preferences at `/api/auth/me/review-preferences`
control new image/audio exercises and US/UK accent without invalidating existing attempts.
The ordinary answer/give-up/confirmation/receipt pipeline remains authoritative.

## Optional mnemonic workflow (5.1.2)

The existing notes router exposes explicit suggestion request/status operations; mnemonic
generation never runs during page load and never writes a note. Owner-bound `mnemonic` jobs
reload visible canonical target/ancestry context, reject changed content, and call only
`services.llm.generate_json`. Its existing private cache, daily budget, JSON validation and
timeout/retry boundary apply. Notes and personal overrides never enter the prompt or shared
cache. The UI displays suggestions separately, requires confirmation before replacing a draft,
and persists a note only on Save. Manual drafting works with generation disabled or offline;
owner-scoped tab drafts survive refresh/navigation with an in-memory storage fallback.

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

## Security boundaries (7.1.3)

The single API process applies bounded anonymous-IP, authenticated-user, authentication-IP and
costly-operation windows before routing; ordinary authorization still checks the current user
and each relevant row, edge and endpoint. Shared dictionary records remain visible only under
their existing `owner = NONE` rules, and administrator account management does not grant access
to another user's learning records. Jobs and protected media are owner-scoped. The regression
matrix and its unavailable Phase 6 backup/import/export paths are documented in
[testing.md](../dev/testing.md#security-isolation-and-production-proxy-713).

The HTTPS edge is Caddy → nginx → API. Nginx enforces same-origin CSP/security headers and serves
media only through authorized internal redirects; only explicitly trusted immediate proxies can
supply client IP/scheme. The deployment's static internal web IP and Caddy trust configuration are
mandatory to separate users safely, not a reason to trust arbitrary forwarded chains. See
[auth.md](auth.md#admission-control-and-privacy-713) and
[deployment.md](../dev/deployment.md#security-proxy-and-headers-713).

## Local development

| Process | How it runs | Port |
|---|---|---|
| SurrealDB dev (persistent) | Podman, `deploy/compose.dev.yml` | 8100 |
| SurrealDB test (in-memory, throwaway) | Podman, same compose file | 8101 |
| API | `uv run uvicorn --reload` on the host | 8000 |
| Worker | `uv run python -m app.worker` on the host | — |
| Web | `pnpm dev` (Vite proxies `/api` → 8000) | 5173 |

## Request flow

### Bounded graph API (4.4.1)

`GET /api/graph?focus_id=<opaque-id>&depth=1` requires authentication. Depth is 0–3;
repeated `node_types` and `relation_types` query parameters restrict traversal, and
`direction=both|outgoing|incoming` controls expansion (default `both`). Empty filter lists
mean all supported types. The focus must be authorized and pass the node filter.
The response contains `focus_id`, `depth`, `direction`, discriminated typed `nodes`,
typed `edges`, effective filter metadata (`node_types`, `relation_types`) and `node_limit: 300`.
Nodes have `{id, table, fields}`; edges have `{id, table, start, end, fields}`.
Effective fields include only the requester's overrides. Ownership is never returned.

Edges retain their stored start→end orientation, independent of expansion direction.
The response is the induced matching graph on the reachable node set; depth 0 therefore
returns the focus and any matching self-edges. Nodes sort by `(table,id)` and edges by
`(table,start,end,id)`. Isolated focuses return one node, not an error.
Malformed/unsupported IDs and invalid filters return 422, missing/unauthorized focuses 404,
and oversized results 413 `graph.too_large` with guidance to reduce depth/filters or hide
unused selections. No arbitrary partial graph is returned. Successful responses are no-store.

### Tag API (4.3.1)

Authenticated `/api/tags` supports POST (201), GET (visible shared/own list),
and `/{id}` GET/PATCH/DELETE (204 for deletion). Shared tag records cannot be changed.
`GET /api/tags/assignments?target_table=...&target_id=...` returns visible tags plus
edge-level `readonly`. `PUT /api/tags/{id}/members` accepts
`{target_table: sense|morpheme|tag, target_id}`; DELETE on that path uses the same query
fields. Both are idempotent 204 operations on only the current owner's memberships.
Request bodies forbid extra fields; tag creation never accepts owner/ID. IDs use the strict
opaque codec. Missing/foreign endpoints return 404, shared-record writes 403, cycles 409.
All successful responses are no-store. Router → service → `db/tags.py` keeps queries at the
repository boundary. API types are generated offline with `dev.ps1 gen-api`.

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

### Private sentence/passage API (4.2.2)

The reading entry `/reading` lists the owner's passages and ingests pasted original text.
`/reading/{opaque-passage-id}` preserves the complete original text, source, sentence ordering
and gaps. `GET /api/content/passage/{id}/reading?project_id={opaque-project-id}` additionally
returns `project_senses`: effective records from the existing owner-safe project tree snapshot,
excluding hidden lemma/lexeme/sense ancestors and unselected senses. Omitting the project
returns an empty selection. Both passage and project ownership are checked independently.
The existing 10,000-membership/2,000-tree-node bounds fail explicitly rather than truncate.
Only resolved occurrences in this effective selection are highlighted; other links are dotted
and unresolved tokens remain plain. Inline dictionary lookup requires an explicit candidate
sense, uses the ordinary project-add API, then confirms the sentence-local occurrence. A
partial failure retains the chosen sense and retries only the unfinished occurrence link.
No provider, private-text cache or new schema is required.

All routes below require the current user, use opaque IDs, return `Cache-Control: no-store`,
and treat foreign/missing/malformed record IDs alike (404).

| Route under `/api/content` | Contract |
|---|---|
| `POST /{kind}` | `ContentCreate` → 201 `ContentRead`; kind is `sentence` or `passage` |
| `GET /{kind}?limit=50&offset=0` | Owner-only list; limit 1–100, offset 0–10000 |
| `GET /{kind}/{id}` | `ContentRead` |
| `PUT /{kind}/{id}` | Full `ContentCreate` replacement; invalidates owned associations |
| `DELETE /{kind}/{id}` | 204; no cascading sentence/dictionary deletion |
| `POST /ingest` | Passage `ContentCreate` → 201 `PassageRead`, atomic and retry-safe |
| `GET /passage/{id}/reading` | `PassageRead` with ordered `SentencePart` spans and occurrences |
| `PUT /passage/{id}/sentences/{order}` | `{sentence_id}` → 204; assign/replace an owned sentence |
| `DELETE /passage/{id}/sentences/{order}` | 204; remove only the owned association |
| `GET /sentence/{id}/occurrences?assist=false` | `AnalysisRead`; offline by default |
| `PUT /sentence/{id}/occurrences` | `Resolution {span, sense_id}` → `AnalysisRead` |
| `DELETE /sentence/{id}/occurrences/{edge_id}` | 204; owner-only used_in unlink |

`ContentCreate` requires nonblank exact `text` (≤20000 code points, ≤2000 tokens), defaults
`lang=en`, `source=""`, `title=""`, `translation={}`. Language keys use a bounded language-tag
pattern. Sentence titles and passage translations are rejected when nonempty. Translation values
are strict strings (≤20000, ≤20 languages), source ≤2000 and title ≤300. Unknown fields are rejected.
Ingestion permits ≤200 sentences and bounds per-token candidate expansion; excessive ambiguity
returns 422, never an arbitrarily chosen sense. Repeated occurrences have distinct local spans.
Resolution requires a full token span and a visible sense; explicit confirmation may select a
visible custom sense outside the lexicon. Suggestions never create associations automatically.
Manual sentence assignment requires both endpoints owned by the actor, order 0–199 identifying
an original split segment, and matching exact sentence text/language. Missing associations leave
gaps without shifting other original spans. DELETE returns 409 if foreign/shared graph edges
would otherwise be removed by the database's automatic endpoint cascade.

`AnalysisRead` contains `sentence`, `occurrences`, `assistance`, `suggestions`. Each occurrence has
original `text`, `span`, candidates (`lemma`, opaque `sense_id`, `definition`), `status`
(`unmatched`, `unresolved` for one unconfirmed candidate, `ambiguous`, `resolved`), nullable
`sense_id` and `edge_id`.
Optional assistance uses the validated LLM service with authenticated owner-scoped inputs and no
shared sources/cache scope. States are `not_requested`, `not_needed`, `available`, or explicit
`unavailable:<reason>`; all core CRUD/ingestion/resolution works without a provider.

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

### Phrase discovery and add flow (4.1.2)

Authenticated `GET /api/dictionary/{table}/{id}/phrases` accepts `lemma` or `lexeme`,
`offset` 0–10,000 and `limit` 1–50 (default 20). It traverses visible `contains` edges
from exact component lexemes; lemma targets first resolve visible `has_lexeme` edges.
The response contains effective phrase entries, canonical offline candidates where available,
source attribution, and `has_more`. Results include only already-materialized phrases,
deduplicated and ordered by stored phrase text then opaque identity. Missing, malformed and
other-owner targets return the same 404. Success is `no-store`; discovery never writes.

Word detail lists these phrases and navigates to the existing lemma route. Phrase add actions
require an explicitly chosen project and open the ordinary add dialog prefilled with phrase
text. The same candidate search, explicit sense selection, materialization, membership, job
and card transaction handles words and phrases; there is no separate phrase membership API.

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

### Exercise attempt API (3.2.1)

Authenticated routes use opaque attempt IDs, owner-scoped services and `Cache-Control: no-store`:

| Route | Request → response |
|---|---|
| `POST /api/exercise-attempts` | `AttemptCreate {project_id, sense_id}` → `201 AttemptRead` |
| `GET /api/exercise-attempts/{id}` | → `AttemptRead` |
| `POST /api/exercise-attempts/{id}/hint` | no body → `AttemptRead` |
| `POST /api/exercise-attempts/{id}/answer` | `AttemptAnswer {answer, duration_ms}` → `AttemptRead` |
| `POST /api/exercise-attempts/{id}/giveup` | `AttemptGiveUp {duration_ms}` → `AttemptRead` |
| `POST /api/exercise-attempts/{id}/confirm` | `AttemptConfirm {rating: 1..4}` → `AttemptRead` |

Generated `AttemptRead` is discriminated by `status`: `AttemptOpen` exposes only
prompt/options/media, requested hint and skip reasons; `AttemptGraded` adds feedback, auto-rating
and validated timing; `AttemptConfirmed` adds the persisted final-rating receipt. No endpoint
accepts client correctness, answer keys, auto-ratings or scheduling versions. The private
`Attempt`, `AnswerSpec`, `FrameworkGrade` and `GradedReview` are absent from OpenAPI.
The framework uses typed plugin contracts and owner-visible selected-lexeme form readers;
later generator tasks register real types without making startup depend on a live provider.
Until registration, creation returns explicit `exercise.no_usable`. See learning-engine.md
for weighting, normalization, timing, expiry and retry semantics.

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

Scenario recall composes `exercise_scenario.register` with the DB/settings-bound
`scenario.acquire` provider. Review requests perform validated cache reads only; misses enqueue
deduplicated owner-scoped `scenario` jobs and expose skip reasons while another eligible type
is selected. `worker.handlers.HANDLERS["scenario"]` reloads the authorized selected content and
checks its version before provider dispatch. Verified shared sources may share cache entries;
effective private/custom definitions remain owner-scoped, and notes are never sent.
Expected provider failures use the generic `JobRejected` terminal-failure contract, preserving
public-safe reason codes through the existing owner-only job status API. No new endpoint,
job-type enum, migration or generated API shape is needed.

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
