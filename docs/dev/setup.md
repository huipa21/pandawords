# Local setup

## Prerequisites (Windows 11)

| Tool | Version | Check |
|---|---|---|
| PowerShell | 7.x (`pwsh`) | `$PSVersionTable.PSVersion` |
| Podman | 5.x, machine running | `podman machine list` |
| Compose provider | docker-compose v2 (used by `podman compose`) | `podman compose version` |
| uv | ≥ 0.11 (installs Python 3.14 itself) | `uv --version` |
| Node.js | 24 LTS | `node --version` |
| pnpm | pinned via `packageManager` in `frontend/package.json` (corepack) | `pnpm --version` |
| git | any recent | `git --version` |

## First run

```powershell
./scripts/dev.ps1 setup      # checks tools, uv python install 3.14, uv sync, pnpm install, .env.dev from .env.example
./scripts/dev.ps1 lexicon    # one-off, downloads ~GBs; builds data/lexicon/lexicon.sqlite (Phase 2+)
./scripts/dev.ps1 up         # DB + migrate + seed + API + worker + Vite
```

Open <http://localhost:5173> and log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env.dev`.

The script resolves the main worktree through Git, so it can be run from a linked worktree and
still uses the main worktree's `.env.dev`. Existing process environment variables take precedence
over values in that file. Run `./scripts/dev.ps1 help` to list the commands currently implemented;
additional commands are added in later foundation tasks.
Setup reports installed tool versions without requiring the Podman machine to be running. To verify
the compose provider, start the machine and run `podman compose version`.

## Daily commands

See the table in [../../AGENTS.md](../../AGENTS.md). The planned `up` command runs the API, worker
and Vite as background jobs and writes logs to `.dev/logs/*.log`; `down` stops them by PID (from
`.dev/pids.json`) and stops the dev DB container. These commands are not implemented yet.

## Local databases

Start the Podman machine and ensure the main worktree's `.env.dev` has `SURREAL_USER` and
`SURREAL_PASS` set. Single-quote passwords containing `$` so Compose reads them literally. From the
main worktree root, start both services and wait for their healthchecks:

```powershell
podman compose --env-file .env.dev --file .\deploy\compose.dev.yml up --detach --wait
```

Both ports bind to IPv4 loopback (`127.0.0.1`) only. `surreal-dev` stores RocksDB data in the named volume
`pandawords-dev-db`; `surreal-test` uses memory and loses its data whenever it restarts. Before
running Compose, check that any existing volume with that name belongs to the `pandawords`
project: Compose can otherwise reuse an unrelated volume. The root credentials initialize a new
datastore; changing them in `.env.dev` does not change an existing root user in the dev volume.

SurrealDB URLs in Settings and `.env.example` use IPv4 loopback to match those bindings:

```dotenv
SURREAL_URL=ws://127.0.0.1:8100/rpc
SURREAL_TEST_URL=ws://127.0.0.1:8101/rpc
```

On Windows, `localhost` can resolve to IPv6 first while Podman forwards only IPv4, causing the
WebSocket handshake to time out. Settings therefore normalizes the literal hostname `localhost`
to `127.0.0.1` in both `SURREAL_URL` and `SURREAL_TEST_URL`, including values from existing
`.env.dev` files; no private file needs editing. External hostnames and explicit IPv6 URLs are
unchanged. Ports, credentials, paths, query strings, and fragments are preserved.

`.\scripts\dev.ps1 reset-db` **deletes all dev database data**. It stops and removes the dev
container, removes its volume, and leaves the test container alone. It refuses to delete a volume
owned by another Compose project or used by another container. An already-absent volume is a
no-op. To start a fresh dev database after a reset:

```powershell
podman compose --env-file .env.dev --file .\deploy\compose.dev.yml up --detach --wait surreal-dev
```

The default Compose project is `pandawords`. For an isolated disposable instance, set both
`COMPOSE_PROJECT_NAME` and `PANDAWORDS_DEV_VOLUME` to unique names in the process environment;
the same values must be present when resetting it. `PANDAWORDS_DEV_PORT` and
`PANDAWORDS_TEST_PORT` optionally change the host ports; update `SURREAL_URL` and `SURREAL_TEST_URL`
accordingly. The inherited process environment takes precedence over `.env.dev`.

The focused database integration test requires ports 8100 and 8101 to be free. It creates a unique
disposable project and volume, writes synthetic records, and inspects and removes only its own
resources:

```powershell
pwsh -NoProfile -File .\scripts\tests\dev-db.Tests.ps1
```

## Ports

| Service | Port |
|---|---|
| Vite | 5173 |
| API | 8000 |
| SurrealDB dev (persistent volume `pandawords-dev-db`) | 8100 |
| SurrealDB test (memory) | 8101 |

## Troubleshooting

- `podman machine start` if the machine is stopped. The default machine has 2 GiB RAM, which is
  enough for SurrealDB.
- Port already in use: `Get-NetTCPConnection -LocalPort 8000` → stop that PID.
- Package downloads are slow or failing: set `PIP_FALLBACK_INDEX_URL` / `NPM_FALLBACK_REGISTRY` in
  `.env.dev`. `uv` and `pnpm` try their official sources first and use these fallbacks only after
  the official source fails.
