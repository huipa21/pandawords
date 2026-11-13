# Deployment

There is no CI and nothing is built on the server. Images are built on the Windows laptop with
Podman, transferred manually, and loaded with Docker on the server (Korea, 2 vCPU / 4 GB / 60 GB).

## Artifacts (`./scripts/dev.ps1 release -Version x.y.z`)

| File | Contents |
|---|---|
| `dist/pandawords-x.y.z-images.tar.gz` | `pandawords-api:x.y.z` and `pandawords-web:x.y.z` (`podman build --platform linux/amd64`, `podman save --format docker-archive --multi-image-archive`, gzip) |
| `dist/pandawords-x.y.z-deploy.tar.gz` | `compose.yml`, `.env.example`, `restore.sh`, `Caddyfile.snippet`, `VERSION` |
| `dist/pandawords-lexicon-<date>.tar.gz` | `lexicon.sqlite` + `manifest.json` (only when the lexicon changes) |

SurrealDB is pulled on the server from the official `surrealdb/surrealdb:v3.3.x` image (pinned patch
version). `DOCKER_REGISTRY_MIRROR` is used only if Docker Hub fails.

The exact `podman save` flags must be verified in task 1.6.5, and the result recorded here.

## Building the application images

Run from the repository root (the web build needs the workspace lockfile and nginx config):

```powershell
podman build --platform linux/amd64 -f backend\Dockerfile -t localhost/pandawords-api:dev backend
podman build --platform linux/amd64 -f frontend\Dockerfile -t localhost/pandawords-web:dev .
```

The backend uses Python 3.14 slim (Debian trixie), uv 0.11.18 and the frozen production
dependencies only. Its runtime user is UID/GID `10001:10001`; writable media mounts at
`/data/media` must permit that UID to write. Mount the lexicon read-only at `/data/lexicon`.
The same backend image supports command overrides for the worker and migrations.
The web build uses Node 24.21.0 Alpine 3.23, the workspace-pinned pnpm, and nginx 1.30 Alpine.
The Dockerfile-specific web ignore file and backend ignore file exclude local dependencies,
build output and environment files.

On the container network the backend must have the alias `api` before nginx starts.
Web serves SPA routes, proxies `/api` without stripping the prefix, compresses text responses,
and caches fingerprinted `/assets/` files immutably for one year (missing assets return 404).
Mount media read-only at `/data/media` in web: direct `/_media/` requests return 404; only a
trusted API response's `X-Accel-Redirect` can serve those files. Liveness is `/api/healthz`;
`/api/readyz` can return 503 when the database is unavailable.

Base-image overrides (`PYTHON_IMAGE`, `UV_IMAGE`, `NODE_IMAGE`, `NGINX_IMAGE`) are available
as build arguments for explicitly configured registry mirrors. Try official registries first;
do not disable TLS verification or change user-wide registry configuration.

## First-time server setup

```bash
mkdir -p /opt/pandawords && cd /opt/pandawords
tar xzf pandawords-x.y.z-deploy.tar.gz
cp .env.example .env && vi .env        # secrets, APP_DOMAIN, CADDY_NETWORK, APP_VERSION=x.y.z
mkdir -p lexicon && tar xzf pandawords-lexicon-<date>.tar.gz -C lexicon
gunzip -c pandawords-x.y.z-images.tar.gz | docker load
docker compose up -d                   # migrate runs first; API waits for it
```

The release command/bundles are task 1.6.5; for a source checkout use
`podman compose --env-file deploy/.env -f deploy/compose.yml up -d`.
Compose resolves `.env` and `lexicon/` beside `compose.yml`. Production overrides in
`.env.example` must replace the development values, with real random secrets.
The images are `pandawords-api:${APP_VERSION}` and `pandawords-web:${APP_VERSION}`.
The external network must already exist and include Caddy. Only web joins it, with
alias `pandawords-web`; there are no host port bindings. All services share an
isolated internal network. API outbound internet access is intentionally unavailable
in this baseline; optional external providers require a deliberate egress design.
The worker service is deferred to task 1.6.2.

Add `Caddyfile.snippet` to your Caddy config and reload Caddy:

```
{$APP_DOMAIN} {
    encode zstd gzip
    reverse_proxy pandawords-web:80
}
```

`web` joins `${CADDY_NETWORK}` (external) with the alias `pandawords-web`. No other service is on
that network.
`APP_DOMAIN` must be available in the **Caddy process** environment; the application
Compose `.env` does not configure an independently managed Caddy container.

The one-shot `migrate` waits for healthy SurrealDB 3.3.5, then uses SDK 3.0's HTTP
export over its authenticated WebSocket session (N21). It writes gzip-compressed
SurrealQL to the `backups` volume as `pre-migrate-<UTC>-<unique>.surql.gz`, closing
and renaming a partial file before invoking the migration runner. Any metadata,
export or disk error fails the service and prevents API startup. Even a fresh empty
database is exported, never silently skipped: verified on 3.3.5, `use()` creates
the selected database, `INFO FOR DB` has empty schema maps, and export returns the
`OPTION IMPORT;` header. The API waits for successful migration; web waits for API
readiness. Web's healthcheck also checks `/api/readyz` through nginx.

The one-shot and SurrealDB run as root, with all capabilities dropped and
no-new-privileges, to write standard root-owned named volumes portably under Docker
and Podman. The upstream SurrealDB image cannot initialize ownership of a fresh
`/data` volume; its default nonroot user otherwise fails with permission denied.
The long-running API remains UID 10001.
Database, media and backups are project-scoped named volumes; lexicon is a read-only
bind mount. Do not run `down -v` on production. Exports contain the selected database
(schema, users, records, edges), not root/namespace credentials or media/lexicon files.
Protect and separately copy those assets and the `.env` file. Keep backup volumes
private, copy exports off-host, and prune only after a newer restore-tested backup
exists. Automatic retention and `restore.sh` are not implemented yet (task 6.1.5).

### Verified local production smoke (task 1.6.4)

Podman with Compose v2.40.3, SurrealDB 3.3.5, API image
`localhost/pandawords-api:task-1.6.4-20261114`, and the verified 1.6.3 web image
retagged `localhost/pandawords-web:task-1.6.4-20261114`:

```powershell
podman network create pw164-caddy
podman compose --env-file deploy\.env -f deploy\compose.yml -p pw164-acceptance up -d --pull never
podman compose --env-file deploy\.env -f deploy\compose.yml -p pw164-acceptance run --rm migrate
podman run --rm --network pw164-caddy localhost/pandawords-api:task-1.6.4-20261114 python -c 'import urllib.request; r=urllib.request.urlopen("http://pandawords-web/api/readyz"); print(r.status,r.read().decode())'
podman compose --env-file deploy\.env -f deploy\compose.yml -p pw164-acceptance down -v
podman network rm pw164-caddy
```

The ignored `deploy/.env` contained synthetic credentials, this task image version,
and `CADDY_NETWORK=pw164-caddy`. Fresh migrations exited 0 (one migration);
the second run exited 0 (no pending migrations). Both produced readable gzip
exports. Restoring the second export into an isolated empty database using
`db.import_()` reproduced database schema and migration records exactly.
Web returned `200 {"status":"ok"}`; all long-running services passed healthchecks.
API UID 10001 could write media; only web joined the Caddy network; no host ports
were published. A read-only `/proc` backup target failed nonzero before migrations.
Default nonroot SurrealDB initially failed with RocksDB permission denied; the
capability-free root configuration above resolved it without host ownership hacks.
Only task-owned project resources and synthetic files were removed after the run;
no dev/test database was used.

## Upgrade

```bash
scp dist/pandawords-x.y.z-*.tar.gz server:/opt/pandawords/
gunzip -c pandawords-x.y.z-images.tar.gz | docker load
sed -i 's/^APP_VERSION=.*/APP_VERSION=x.y.z/' .env
docker compose up -d                   # migrate makes a pre-migration backup, then applies migrations
```

## Rollback

Migrations only move forward. If a release has to be reverted after migrating:

1. `docker compose down`.
2. Decompress the selected `pre-migrate-<UTC>-<unique>.surql.gz` from the backups
   volume and restore with SDK `await db.import_(sql)` into a separate empty database,
   retaining `OPTION IMPORT;` (N21). Restore media separately. Automated `restore.sh`
   remains task 6.1.5; do not assume these exports are tar archives.
3. Set the previous `APP_VERSION` and run `docker compose up -d`.

## Resource limits (compose)

| Service | Memory limit |
|---|---|
| surrealdb | 1.5 GB |
| api | 768 MB |
| migrate | 768 MB (one-shot, completes before API starts) |
| worker | 768 MB (spaCy sm + edge-tts) |
| web | 64 MB |

Uvicorn runs with 1 worker. The total leaves headroom for Caddy and the OS.
