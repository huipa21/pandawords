# Phase 1 — Foundation: task details

The format for each task is Goal · Deliverables · Acceptance · Docs. Dependencies and waves are in
[PLAN.md](PLAN.md).

## 1.1 Repository & tooling

### 1.1.1 Initialize repository
- **Goal:** a clean `main` branch holding the docs, ready for task branches.
- **Deliverables:**
  - A `main` branch with an initial commit. `.git` already exists with no branches, so don't
    re-init and don't touch `refs/agents`.
  - `.gitignore`: `data/`, `dist/`, `.dev/`, `.env*` except `!.env.example`, `node_modules/`,
    `.venv/`, `__pycache__/`, `*.sqlite` except `backend/tests/fixtures/*.sqlite`, Playwright and
    coverage output.
  - `.gitattributes`: `* text=auto eol=lf`, binary for images, audio and sqlite.
  - `.editorconfig`.
  - `.env.example`, with the same keys as `.env.dev` and safe placeholders.
  - Root `README.md` (short; links to AGENTS.md and docs).
- **Acceptance:**
  - `git log` shows the initial commit on `main` and `git status` is clean.
  - `git check-ignore .env.dev` matches.
  - Ask the user for a GitHub remote URL, and add it only if they provide one.
- **Docs:** conventions.md (Git)

### 1.1.2 `dev.ps1` skeleton
- **Goal:** one entry point for every dev command, working from any worktree.
- **Deliverables:** `scripts/dev.ps1` (PowerShell 7) with:
  - Subcommand dispatch and `help`.
  - Resolution of the main worktree root (`git rev-parse --path-format=absolute --git-common-dir`
    → parent), loading `.env.dev` from there.
  - `setup`: checks tools and prints their versions, runs `uv python install 3.14`, and runs
    `uv sync` / `pnpm install` when `backend/` / `frontend/` exist. Creates `.env.dev` from
    `.env.example` if it's missing.
  - Helpers: quiet runner (full output on failure), `.dev/` logs dir, a retry wrapper that uses the
    `*_FALLBACK_*` sources only after the official source fails.
- **Acceptance:**
  - `help` lists the commands.
  - `setup` succeeds on this laptop.
  - Run from a worktree folder, it loads the main `.env.dev`.
- **Docs:** setup.md, workflow.md (shared resources)

### 1.1.3 lefthook pre-commit
- **Goal:** catch lint errors and leaked secrets before a commit.
- **Deliverables:**
  - `lefthook.yml` running `ruff format --check` and `ruff check` on staged `*.py`, eslint on staged
    `*.{ts,vue}`, and a guard that blocks staged `.env*` except `.env.example`.
  - lefthook installed through the root pnpm workspace dev dependency, with `lefthook install`
    added to `dev.ps1 setup`.
- **Acceptance:**
  - Committing a badly formatted file fails.
  - Staging `.env.dev` (with `git add -f`) is blocked.
- **Docs:** conventions.md

### 1.1.4 VS Code workspace
- **Deliverables:**
  - `.vscode/settings.json`: search and watcher excludes (`data`, `dist`, `.dev`, `node_modules`,
    `.venv`, `frontend/src/api/schema.d.ts`, lockfiles), Python interpreter `backend/.venv`, eslint
    flat config, UnoCSS.
  - `.vscode/extensions.json`: Vue - Official, ESLint, UnoCSS, Ruff, Python, Playwright.
- **Acceptance:** searching in VS Code skips the generated and data folders.

## 1.2 Backend skeleton

### 1.2.1 Backend uv project
- **Deliverables:**
  - `backend/pyproject.toml`: `requires-python = ">=3.14,<3.15"`. Foundation dependencies only:
    fastapi, uvicorn[standard], pydantic, pydantic-settings, surrealdb>=3.0,<4, structlog, orjson,
    pyjwt, pwdlib[argon2], httpx, python-multipart. Dev: ruff, basedpyright, pytest, anyio.
  - `.python-version` (3.14), `uv.lock`.
  - Ruff config (line length 100, a sensible rule set), basedpyright config, pytest config
    (`anyio` backend, markers `integration`, `fresh_db`).
  - `app/__init__.py`.
- **Acceptance:** `uv sync`, `uv run ruff check`, `uv run basedpyright` and `uv run pytest -q` all
  succeed on Python 3.14.
- **Docs:** conventions.md (Python)

### 1.2.2 API skeleton
- **Deliverables:**
  - `app/main.py` with `create_app()` and the lifespan hook.
  - `core/config.py`: Settings covering every `.env.example` key, with dev env-file resolution.
  - `core/logging.py`: structlog, JSON in prod and console in dev, with request-id middleware.
  - `core/errors.py`: `AppError(code, status, message, field)` and its handlers. Validation errors
    become `validation.invalid` with `field`.
  - `GET /api/healthz` and `GET /api/readyz` (a stub until 1.2.3). OpenAPI at `/api/openapi.json`.
  - `python -m app.openapi` prints the schema without starting a server.
- **Acceptance:**
  - API tests cover healthz and the error response shape.
  - `uv run uvicorn app.main:app` starts.
- **Docs:** overview.md, conventions.md (API)

### 1.2.3 SurrealDB client lifecycle
- **Deliverables:**
  - `app/db/client.py`: one AsyncSurreal WebSocket connection per process, with sign-in, namespace
    and database selection, and reconnect with backoff.
  - A `get_db` dependency.
  - `readyz` runs a trivial query.
- **Acceptance:** an integration test against `SURREAL_TEST_URL` gets 200 when the DB is up and 503
  when the URL is unreachable.
- **Docs:** surrealdb-notes.md (N02, N03)

## 1.3 Database & migrations

### 1.3.1 Podman dev/test SurrealDB
- **Deliverables:**
  - `deploy/compose.dev.yml` with `surreal-dev` (RocksDB, volume `pandawords-dev-db`, port 8100)
    and `surreal-test` (memory, port 8101).
  - The image pinned to the latest `surrealdb/surrealdb:v3.3.x` patch, recorded in ADR 0001's
    notes, with healthchecks.
  - Internal `dev.ps1` DB functions plus `reset-db`.
- **Acceptance:**
  - Both containers are healthy under `podman compose`.
  - `reset-db` wipes the dev data.
- **Docs:** setup.md

### 1.3.2 SurrealQL verification spike
- **Goal:** replace beliefs with facts before building on them.
- **Deliverables:** `backend/scripts/verify_surreal.py`, which runs N01–N23 against the test
  instance (kept as a regression aid). Update `surrealdb-notes.md`: set each row's status and
  version, and add copy-paste snippets under "Verified snippets".
- **Acceptance:**
  - Every row is ✅, or ❌ with a working alternative.
  - The rows the migration runner and tests rely on (N07, N08, N16, N20, N23) are resolved.
  - N21 (export) is resolved for 1.6.4.
- **Docs:** surrealdb-notes.md, surrealql.instructions.md

### 1.3.3 Migration runner
- **Deliverables:**
  - `app/db/migrate.py` with the CLI `python -m app.db.migrate [--dry-run]`.
  - The runner:
    - creates `_migration` if it's missing
    - discovers `NNNN_*.surql` / `NNNN_*.py` files and computes their sha256
    - refuses to run if an applied file's checksum has changed
    - applies pending files in order, each in a transaction (or with the documented N16
      workaround), and records them
  - `0001_bootstrap.surql` (namespace/database-level definitions as needed).
- **Acceptance (integration tests):**
  - It applies to a fresh DB.
  - A second run does nothing.
  - An edited applied file fails with a clear error.
  - A failing migration leaves no partial state and is not recorded.
- **Docs:** ADR 0010, surrealql.instructions.md

### 1.3.4 Schema snapshot + drift test
- **Deliverables:**
  - `app/db/snapshot.py`, which turns `INFO FOR DB` and `INFO FOR TABLE` into normalized,
    sorted-key JSON.
  - The committed file `backend/app/db/schema.snapshot.json`.
  - A drift test, plus `dev.ps1 test -Backend -UpdateSnapshot`.
- **Acceptance:** adding a migration without updating the snapshot fails the test, and the error
  shows a readable diff.

### 1.3.5 Test harness
- **Deliverables:**
  - pytest fixtures for a session database `t_<worktree-short>_<random8>` in namespace
    `pandawords_test`, migrated once and removed at the end.
  - The `fresh_db` marker, which gives a test its own database.
  - A `client` fixture (httpx `ASGITransport`, with the app wired to the test DB).
  - A `make_user` factory hook, finished in 1.5.x.
  - `dev.ps1 test -Backend` starts the test container if it's down.
- **Acceptance:** two simultaneous pytest runs (simulating two worktrees) pass without interfering
  with each other.
- **Docs:** testing.md

## 1.4 Frontend skeleton

### 1.4.1 Frontend project
- **Deliverables:**
  - Root `package.json` (private, tooling only) and `pnpm-workspace.yaml` (member `frontend`).
  - `frontend/` with Vite 8, Vue 3.5, TypeScript **6.0.x pinned** and vue-tsc, plus a
    `packageManager` field.
  - The `@/` alias, a Vite proxy from `/api` to `:8000`, `@antfu/eslint-config` (flat), and vitest.
  - Scripts: `dev`, `build`, `typecheck`, `lint`, `test`.
- **Acceptance:** `build`, `typecheck`, `lint` and `test` pass on a hello page.
- **Docs:** ADR 0008, frontend.instructions.md

### 1.4.2 Design tokens
- **Deliverables:**
  - `src/design/tokens.ts`, exactly as in `docs/ui/tokens.md`.
  - Generators: CSS vars (`:root` / `[data-theme='dark']`), `naive-theme.ts` (light and dark
    overrides including radius and control heights), and the `uno.config.ts` theme. The theme
    replaces the default palette, font sizes, radius and shadows, and includes the `blocklist` for
    arbitrary values and default colors.
  - A `cytoscape-style.ts` stub.
  - `@fontsource-variable` Roboto, Roboto Serif, Noto Sans and Roboto Mono.
  - A lint rule for hex/rgb/px literals in SFC `<style>` and inline styles.
- **Acceptance:**
  - A vitest test checks that the light and dark themes define the same token keys.
  - A sample using `p-[13px]` or `bg-red-500` is rejected by the build or lint.
  - Every value in `tokens.ts` matches `tokens.md`.
- **Docs:** tokens.md, ADR 0011

### 1.4.3 App shell
- **Deliverables:**
  - `src/app/` with main.ts, router (an auth layout and an app layout), Pinia, and vue-i18n
    (`zh-CN` default, `en`).
  - A preferences store: theme system/light/dark, persisted, following `prefers-color-scheme`.
  - `NConfigProvider` with the theme overrides, kept in sync with `data-theme`.
  - `AppShell`: header, sidebar from `lg` up, bottom nav below `lg`, and the Naive providers.
  - `ThemeToggle` and `LocaleSwitch`.
  - Placeholder pages for the routes in overview.md.
  - unplugin-icons (Lucide) and unplugin-vue-components (Naive resolver).
- **Acceptance:**
  - The toggle switches both the Naive UI theme and the CSS vars.
  - The layout is correct at 375px and 1280px wide.
  - A vitest test covers the system-follow logic.
- **Docs:** patterns.md, components.md (app components)

### 1.4.4 `/dev/design` preview page
- **Deliverables:** a dev-only route showing token swatches (light and dark), the type scale,
  spacing, radius, shadows, the Naive components in use, and the app components. It is registered
  only when `import.meta.env.DEV`.
- **Acceptance:** the page renders, and the production build contains no dev-design chunk.

### 1.4.5 API types pipeline + client
- **Deliverables:**
  - `dev.ps1 gen-api`: `uv run python -m app.openapi` → `frontend/src/api/openapi.json` →
    openapi-typescript → `schema.d.ts`. Both files are committed.
  - `src/api/client.ts` (openapi-fetch):
    - attaches the access token
    - on a 401, does one shared refresh and then retries the request
    - logs out if the refresh fails
    - normalizes errors to `{code, message, field}`
- **Acceptance:** vitest (mocked fetch) checks that concurrent 401s trigger exactly one refresh.

## 1.5 Auth & users

### 1.5.1 Migration: user, refresh_token
- **Deliverables:** `0002_auth.surql` (fields from data-model.md, a unique `username` index, and a
  unique `token_hash` index) and the updated snapshot.
- **Acceptance:** an integration test shows a duplicate username is rejected.

### 1.5.2 Security core
- **Deliverables:**
  - `core/security.py`: argon2id hash/verify via pwdlib; JWT encode/decode with `sub`, `role`,
    `exp` and `iat`; refresh token generation plus its sha256.
  - `services/auth.py`: login, refresh rotation with reuse detection (reuse revokes the whole
    chain), and logout.
  - The admin bootstrap in the lifespan hook.
- **Acceptance:**
  - Unit tests cover expired and tampered JWTs.
  - Integration tests cover rotation, reuse revoking the chain, and the bootstrap running exactly
    once.
- **Docs:** auth.md, ADR 0006

### 1.5.3 Auth API
- **Deliverables:**
  - The endpoints listed in auth.md.
  - The refresh cookie: httpOnly, `Secure` in prod, `SameSite=Strict`, path `/api/auth`.
  - `current_user` and `require_admin` dependencies.
  - A `must_change_password` gate: everything except `me`, `password` and `logout` returns
    403 `auth.password_change_required`.
  - Login backoff.
- **Acceptance (API tests):**
  - A successful login works, and failed logins return the same generic error.
  - Refresh and logout work.
  - The forced-change gate works.
  - A disabled user is rejected.

### 1.5.4 Admin users API
- **Deliverables:**
  - List (paginated).
  - Create (temporary password, `must_change_password`).
  - Patch: disable/enable, role, reset password.
  - Guards: an admin can't disable or demote themselves or the last admin.
- **Acceptance:** API tests cover a non-admin getting 403 and the last-admin protection.

### 1.5.5 Frontend auth
- **Deliverables:**
  - Login page (NForm).
  - Auth store: the access token in memory only, and a session restore on page load by calling
    refresh.
  - Route guards: authenticated, admin, and a forced redirect to change the password.
  - Change-password page, logout, and the i18n strings and error-code mapping.
- **Acceptance:**
  - vitest covers the guard logic.
  - The flow works against the dev API.
- **Docs:** patterns.md (forms)

### 1.5.6 Frontend admin users page
- **Deliverables:**
  - An NDataTable on desktop and a card list on mobile.
  - A create-user modal that shows the generated temporary password with copy.
  - Disable/enable, reset password and role change, with ConfirmAction on destructive actions.
- **Acceptance:** every action works against the API, and the page is correct at 375px and 1280px.

## 1.6 Dev environment & packaging

### 1.6.1 `dev.ps1` `up` / `down` / `check` / `test`
- **Deliverables:**
  - `up`: start the dev DB, run migrations, seed (dev seeds folder), then start the API
    (`--reload`), the worker and Vite as background processes. PIDs go in `.dev/pids.json` and logs
    in `.dev/logs/`. It prints the URLs.
  - `down`: stop by PID.
  - `check`: ruff format --check, ruff, basedpyright, eslint, vue-tsc.
  - `test` with `-Backend`, `-Frontend` and `-E2E`. Output is quiet, with full details on failure,
    and the exit code is non-zero on failure.
- **Acceptance:**
  - From a clean state, `up` gives a working login page.
  - After `down`, no processes are left.
  - `check` fails on an introduced lint error.

### 1.6.2 Worker skeleton + jobs
- **Deliverables:**
  - `0003_job.surql`.
  - `services/jobs.py`: enqueue, and an atomic claim using a conditional UPDATE.
  - `app/worker`: a loop that wakes on LIVE notifications (polling every 5 s as a fallback), a
    handler registry, exponential-backoff retries, max attempts, and graceful shutdown.
  - A `noop` handler.
  - `GET /api/jobs/{id}`, scoped to the owner.
  - The `worker` service added to `deploy/compose.yml`.
- **Acceptance (integration tests):**
  - Two concurrent workers claim a job exactly once.
  - Retries and backoff work.
  - The jobs API is isolated between users.

### 1.6.3 Dockerfiles
- **Deliverables:**
  - `backend/Dockerfile`: multi-stage. `uv sync --frozen --no-dev`, a `python:3.14-slim` runtime,
    and a non-root user.
  - `frontend/Dockerfile`: a `node:24-alpine` pnpm build, then `nginx:alpine`.
  - `deploy/nginx.conf`:
    - SPA fallback
    - `/api` proxied to `api:8000`
    - gzip
    - immutable cache headers on hashed assets
    - an internal `/_media/` location for X-Accel-Redirect
- **Acceptance:**
  - Both images build with `podman build --platform linux/amd64`.
  - In a smoke run, the API's `/api/healthz` returns 200 and web serves the index page.

### 1.6.4 Production compose
- **Deliverables:**
  - `deploy/compose.yml`:
    - services `web`, `api`, `migrate` (one-shot) and `surrealdb` (pinned `v3.3.x`)
    - `env_file: .env` and `${APP_VERSION}` image tags
    - healthchecks, and `depends_on` with `service_completed_successfully` for `migrate`
    - memory limits from deployment.md
    - volumes
    - an internal network plus the external `${CADDY_NETWORK}` (only `web`, alias `pandawords-web`)
  - `migrate` exports the site to the backups volume before it applies pending migrations, using
    the N21 result.
  - A production section in `.env.example`, and `deploy/Caddyfile.snippet`.
- **Acceptance:**
  - `podman compose -f deploy/compose.yml up` works locally with a stand-in external network.
  - `/api/readyz` returns 200 through `web:80`.
  - The migrate service completes.

### 1.6.5 `dev.ps1 release`
- **Deliverables:** `release -Version x.y.z`:
  - builds and tags both images
  - saves them as a gzipped multi-image docker-archive
  - creates the deploy bundle (`compose.yml`, `.env.example`, `Caddyfile.snippet`, `VERSION`;
    `restore.sh` comes in 6.1.5)
  - writes `SHA256SUMS`
- **Acceptance:**
  - The archive loads back into a clean podman image store.
  - `deployment.md` is updated with the verified commands.

### 1.6.6 E2E: first-login flow
- **Deliverables:** Playwright config (base URL 5173, run against the `up` stack) and one test:
  admin logs in → creates a user → logs out → the user logs in → is forced to change the password →
  lands on `/projects`.
- **Acceptance:** `dev.ps1 test -E2E` passes on `main`.
