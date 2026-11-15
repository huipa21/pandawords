# Deployment

## Frontend transfer budget (7.1.4)

Node 24/Vite 8 production manifest measurements, including the PWA install script,
use nginx gzip level 1. Before/after initial JS: 183,977 -> 181,846 bytes; CSS:
4,715 -> 4,593. Lazy layouts and project graph splitting reduce project-tree JS
501,680 -> 246,342 bytes. Project graph remains 505,881, all words 469,769 and
login 210,451 after the change (before: 501,680 / 466,293 / 209,650).
Total static JS increases slightly (642,452 -> 647,424 bytes) because of splitting.
First PWA install precaches 78 files / 2,331,222 raw bytes / 1,116,445 modeled
transfer bytes (before: 69 / 2,326,525 / 1,111,148), plus 5,131 worker transfer
bytes. This background traffic is separate from foreground initial JS; it is not
a first-install bandwidth saving. Actual wire bytes also include HTTP overhead.
The build enforces explicit budgets documented in [testing.md](testing.md).

## Image request limits

Nginx permits **11 MiB** request bodies (`client_max_body_size 11m`), leaving 1 MiB
headroom over the **10 MiB encoded image** ceiling for proxy/multipart overhead. The
image upload API itself accepts raw encoded JPEG/PNG/WebP/GIF bytes, not multipart, and
enforces its ceiling while streaming irrespective of `Content-Length`. Pillow decodes every
frame: at most 25 million pixels/frame, 100 frames and 50 million total pixels.
Do not expose `/_media/` publicly or replace protected media delivery with provider hotlinks.
`PIXABAY_API_KEY` stays server-side; omitting it leaves ordinary upload fully functional.

The API image seeds `/data/media/.initialized` before switching to UID/GID 10001.
Keep this marker: with a completely empty fresh Podman volume, a later root nginx mount
can reinitialize ownership to 0:0, making API uploads fail despite its read-only mount.
A nonempty API-owned copy-up preserves ownership; do not make the API root or broadly chmod
the media volume. Existing incorrectly owned volumes require inspection before manual repair.
Run the real-proxy regression against a locally built API image:

```powershell
.\scripts\test-image-proxy.ps1 -ApiImage localhost/pandawords-api:your-validation-tag
```

It uses the actual nginx configuration, isolated containers/network/fresh media volume,
generated secrets, mocked-out optional providers and an in-memory throwaway database. It
checks an exact 10 MiB upload, protected byte-identical delivery, 10 MiB+1 rejection, deletion
and subsequent 404, then cleans up only its own resources. Required local images:
the supplied API image, nginx 1.30-alpine and SurrealDB 3.3.5; pulling is disabled.

There is no CI and nothing is built on the server. Images are built on the Windows laptop with
Podman, transferred manually, and loaded with Docker on the server (Korea, 2 vCPU / 4 GB / 60 GB).

## Artifacts (`./scripts/dev.ps1 release -Version x.y.z`)

| File | Contents |
|---|---|
| `dist/pandawords-x.y.z-images.tar.gz` | `pandawords-api:x.y.z` and `pandawords-web:x.y.z` (`podman build --platform linux/amd64`, `podman save --format docker-archive --multi-image-archive`, gzip) |
| `dist/pandawords-x.y.z-deploy.tar.gz` | `compose.yml`, `.env.example`, `Caddyfile.snippet`, `VERSION` (`restore.sh` deferred to 6.1.5) |
| `dist/SHA256SUMS` | SHA-256 checksums of the two release archives, with relative filenames |
| `dist/pandawords-lexicon-<date>.tar.gz` | `lexicon.sqlite`, `manifest.json`, `SHA256SUMS` (`dev.ps1 lexicon`, only when the lexicon changes) |
| `dist/pandawords-lexicon-<date>.tar.gz.sha256` | SHA-256 of that lexicon archive; independent of application-release `SHA256SUMS` |

SurrealDB is pulled on the server from the official `surrealdb/surrealdb:v3.3.x` image (pinned patch
version). `DOCKER_REGISTRY_MIRROR` is used only if Docker Hub fails.

Run `pwsh -NoProfile -File scripts\dev.ps1 release -Version 0.1.0` from this worktree.
PowerShell 7.3+ supplies the native .NET tar/gzip APIs; no archiver package is installed.
Versions must be exactly three nonnegative integers without leading zeros (no suffixes,
whitespace or shell syntax). Existing artifacts, `SHA256SUMS`, concurrent releases, and
existing release image tags are refused rather than overwritten. Move the complete previous
release out of `dist/` before building another. A failed build leaves no published artifacts;
any images already built remain cached, so retry with a new version. `dist/` is gitignored.

Release builds use the Dockerfiles' official registries and `--tls-verify=true`; they do not
silently retry against mirrors or change registry configuration. If an official build fails,
diagnose that failure before considering an explicitly configured fallback.

The archive uses explicit `docker.io/library/pandawords-{api,web}:x.y.z` tags, not Podman's
implicit `localhost/` prefix. These identify the same Docker images as the unqualified
`pandawords-{api,web}:x.y.z` names in production Compose.

### Lexicon transfer

Run `.\scripts\dev.ps1 lexicon [-Date yyyy-MM-dd]` explicitly after installing dependencies.
It uses the selected worktree's code and the main worktree's ignored data/output locations,
verifies or downloads official sources, then builds with ECDICT, wordfreq and OEWN. For
snapshot/output overrides and overwrite guards, see [setup.md](setup.md#lexicon-release).
No containers or application images are needed. Both archive and sidecar must be absent
before publication; failures identify their stage and do not leave partial releases.

Transfer both files, then verify on the server before installing into the read-only lexicon
mount. Use a new unpack directory rather than replacing a running database in place:

```sh
sha256sum -c pandawords-lexicon-2026-11-14.tar.gz.sha256
mkdir lexicon-2026-11-14
tar -xzf pandawords-lexicon-2026-11-14.tar.gz -C lexicon-2026-11-14
(cd lexicon-2026-11-14 && sha256sum -c SHA256SUMS)
sqlite3 lexicon-2026-11-14/lexicon.sqlite 'PRAGMA integrity_check; PRAGMA foreign_key_check;'
```

The SQLite checks must print `ok` and no foreign-key rows. The manifest includes original
download records/licenses, all source attributions, installed wordfreq version, database
schema version, size, hash and build counts. Keep it alongside the database. The lexicon is
a separately transferred rebuildable artifact, **not part of site backups**; no backup
command or retention policy changes.

### Verified release round trip (task 1.6.5)

Verified with PowerShell 7.7.0, Podman client 5.8.2 / VM 5.8.4:

```powershell
pwsh -NoProfile -File scripts\tests\release.Tests.ps1
pwsh -NoProfile -File scripts\dev.ps1 release -Version 0.1.165
# The helper builds both images with --platform linux/amd64, then executes:
podman save --format docker-archive --multi-image-archive --output images.tar docker.io/library/pandawords-api:0.1.165 docker.io/library/pandawords-web:0.1.165
# images.tar is compressed with .NET GZipStream, not a PowerShell text pipeline.
tar -tzf dist\pandawords-0.1.165-deploy.tar.gz
tar -xOf dist\pandawords-0.1.165-images.tar.gz manifest.json
```

`manifest.json` contained exactly two entries:

| RepoTag | Config / image ID (SHA-256, before and after load) |
|---|---|
| `docker.io/library/pandawords-api:0.1.165` | `7e01eb7292ab18b8f0039b622e8e1cec17ab09b1f2616cda1f8a201199f102a4` |
| `docker.io/library/pandawords-web:0.1.165` | `74d476130c8e3b2612edad99b38b2fc636edc2b885364c2c40b492240457a1bf` |

Both configs were `linux/amd64`. Deploy members were exactly `.env.example`,
`Caddyfile.snippet`, `compose.yml`, `VERSION`; `VERSION` contained `0.1.165` plus LF.
The example is copied from the repository root, not from any local `.env`.

The produced `SHA256SUMS` was verified with `sha256sum -c SHA256SUMS` from `dist/`:

```text
0f5f92f1189c2b36047901c335ac12882f46af9a192e8d95c7a485a9998256a6  pandawords-0.1.165-images.tar.gz
6e2de6a563bba47156ef3a286f19468a2b5bc24b94a8caa46b1578e36aeaf7b8  pandawords-0.1.165-deploy.tar.gz
```

Clean-store acceptance ran the following shell via `podman machine ssh` in the rootful
Linux VM (adjust the shared worktree path on another laptop). A unique 4 GiB tmpfs mounted
under the worktree gives the disposable VFS store native Linux permissions, without using
the shared `/var/lib/containers/storage`. No shared images were removed, pruned or reset:

```sh
set -eu
cd /mnt/c/other/pandawords.worktrees/1.6.5
scratch="$PWD/.dev/release-load-0.1.165"
mkdir "$scratch"
mount -t tmpfs -o size=4G,nosuid,nodev tmpfs "$scratch"
trap 'umount "$scratch"; rmdir "$scratch"' EXIT
p() { podman --root "$scratch/store" --runroot "$scratch/run" --storage-driver vfs --events-backend none "$@"; }
test -z "$(p images -q)"
(cd dist && sha256sum -c SHA256SUMS)
timeout 180 podman --root "$scratch/store" --runroot "$scratch/run" --storage-driver vfs --events-backend none load --input "$PWD/dist/pandawords-0.1.165-images.tar.gz"
test "$(p images -q | sort -u | wc -l)" -eq 2
p image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}} {{.RepoTags}}' docker.io/library/pandawords-api:0.1.165 docker.io/library/pandawords-web:0.1.165
```

`load --input` accepted gzip directly, loaded both images, and preserved the above IDs.
The empty-store check, both archive hashes, image count and platform checks passed.
The tmpfs was unmounted and the disposable directory removed afterward. The first checksum
attempt ran from the wrong directory and failed before loading; rerunning from `dist/`
passed. This verifies Podman import, not a live Docker daemon or production deployment.

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
Production Compose starts `worker` with `python -m app.worker`, after successful migration
and database health, on the internal network with the same media/lexicon mounts as the API.
It runs as the image's non-root user, exposes no port and has a 30-second shutdown grace period.
The skeleton registry includes `noop`; register future handlers in `app.worker.handlers`.
LIVE notifications are wakeup hints; the worker scans due queued jobs at least every five
seconds and recreates a disconnected LIVE subscription after five seconds. A conditional
UPDATE is the only claim authority, so concurrent worker processes cannot execute the same
claim. Failed handlers retry after 1, 2, 4 and 8 seconds, then fail permanently on attempt five.
Unknown handler types fail immediately. Persisted/API errors are fixed safe codes, not
exception messages; payloads and owners are omitted from the authenticated status endpoint.
SIGINT/SIGTERM cancels the current handler, schedules a bounded retry (or terminal failure
at the limit), kills LIVE and closes both connections. Handlers must propagate cancellation
and tolerate retries: external side effects are not exactly-once transactions.
A forced kill, machine crash, or DB outage during completion can leave a job `running`;
there is deliberately no lease/reaper in this skeleton. After confirming the old worker is
stopped, an operator must inspect/requeue such a job, respecting its attempt limit. Do not
automatically replay possibly completed external effects.
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
sha256sum -c SHA256SUMS
tar xzf pandawords-x.y.z-deploy.tar.gz
cp .env.example .env && vi .env        # secrets, APP_DOMAIN, CADDY_NETWORK, APP_VERSION=x.y.z
mkdir -p lexicon && tar xzf pandawords-lexicon-<date>.tar.gz -C lexicon
gunzip -c pandawords-x.y.z-images.tar.gz | docker load
docker compose up -d                   # migrate runs first; API waits for it
```

For a source checkout use `podman compose --env-file deploy/.env -f deploy/compose.yml up -d`.
Compose resolves `.env` and `lexicon/` beside `compose.yml`. Production overrides in
`.env.example` must replace the development values, with real random secrets.
The images are `pandawords-api:${APP_VERSION}` and `pandawords-web:${APP_VERSION}`.
The external network must already exist and include Caddy. Only web joins it, with
alias `pandawords-web`; there are no host port bindings. All services share an
isolated internal network. API outbound internet access is intentionally unavailable
in this baseline; optional external providers require a deliberate egress design.
The worker service uses the API image and runs `python -m app.worker`; Compose starts it after
the database is healthy. Development `dev.ps1 up` runs the worker locally; dev seeds are never
part of production startup.

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

### Phase 1 integrated acceptance

The completed auth/admin frontend and API/worker images were rebuilt on 2026-11-14.
An isolated production Compose project passed configuration validation, fresh migration,
API readiness through the stand-in Caddy network, and worker startup as UID 10001.
A separate disposable database proved the production image's worker executes `noop` once
and stops gracefully. Worker is a top-level service, not an API `depends_on` entry.
All smoke containers, volumes and networks were removed afterward.

Release acceptance version `0.1.6913` produced exactly two `linux/amd64` images and the four
documented deployment members. Both SHA-256 checks and a load into an initially empty
tmpfs/VFS image store passed; the store was unmounted and removed without changing shared
images. When piping a shell script through PowerShell to `podman machine ssh bash -s`,
end it with a shell comment: the pipeline's trailing CRLF must not become part of the last
command's argument.

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

### Authenticated media delivery

`GET /api/media/{rid}` requires a bearer token and authorizes both the media and its target.
In production, the API returns only `X-Accel-Redirect: /_media/audio/<generated name>` (or `image/`),
the validated content type and private/no-store caching. Existing nginx `/_media/`
is `internal` with `alias /data/media/`; do not expose that location publicly.
API/worker `MEDIA_DIR` must identify the same volume mounted read-only at `/data/media`
in web. Only trusted application producers may write to it: paths and directory links
are rejected, but the shared filesystem must not permit untrusted concurrent mutations.
Missing or inaccessible media returns a generic 404, never an absolute filesystem path.
In development, the same authorized endpoint streams the validated file through FastAPI so
the Vite proxy works without nginx. Production continues to offload bytes to nginx.
Browser players must fetch with the authenticated API client and use an object URL; a raw
media URL does not carry the required bearer header. There is no public upload endpoint.
