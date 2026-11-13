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
docker compose up -d                   # migrate runs first; api/worker wait for it
```

Add the snippet to your Caddy config and reload Caddy:

```
{$APP_DOMAIN} {
    encode zstd gzip
    reverse_proxy pandawords-web:80
}
```

`web` joins `${CADDY_NETWORK}` (external) with the alias `pandawords-web`. No other service is on
that network.

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
2. Restore the pre-migration backup with `./restore.sh backups/pre-migrate-<ts>.tar.gz`.
3. Set the previous `APP_VERSION` and run `docker compose up -d`.

## Resource limits (compose)

| Service | Memory limit |
|---|---|
| surrealdb | 1.5 GB |
| api | 768 MB |
| worker | 768 MB (spaCy sm + edge-tts) |
| web | 64 MB |

Uvicorn runs with 1 worker. The total leaves headroom for Caddy and the OS.
