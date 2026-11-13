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

## Daily commands

See the table in [../../AGENTS.md](../../AGENTS.md). `up` runs the API, worker and Vite as
background jobs and writes logs to `.dev/logs/*.log`. `down` stops them by PID (from
`.dev/pids.json`) and stops the dev DB container.

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
  `.env.dev`. They are used only after the official source fails.
