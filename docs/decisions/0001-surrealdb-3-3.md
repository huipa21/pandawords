# 0001 — SurrealDB 3.3.x now, 4.x later

**Status:** Accepted (2026-11-13)

**Context.** SurrealDB 4.0 was released in early November 2026. It introduces a new protocol,
replaces RocksDB with SurrealKV, and the upgrade is one-way. The Python SDK `surrealdb` 3.0.0
(released 2026-11-04) documents server v3.3.0+ features and doesn't claim 4.0 support. The AI
agent's knowledge of 3.x/4.x SurrealQL is limited.

**Decision.** Use SurrealDB **3.3.x** (pinned patch, RocksDB storage) with SDK 3.0.x. Keep all
SurrealQL in `backend/app/db/`. Verify syntax against a real server and record it in
`docs/dev/surrealdb-notes.md`.

**Implementation notes (2026-11-13).** Pin the dev and test images to
`surrealdb/surrealdb:v3.3.5`, the latest stable 3.3 patch in the
[official Docker Hub tags](https://hub.docker.com/r/surrealdb/surrealdb/tags?name=v3.3) at the
time of verification. The official image is distroless, so Compose healthchecks use the
`/surreal is-ready` executable directly rather than a shell. Dev uses RocksDB; test uses memory.
The image runs as UID/GID 65532, so the Podman local volume is created with matching ownership.
Unused image-declared volume paths use tmpfs to avoid leaving anonymous volumes behind.

**Consequences.** Upgrading to 4.x later means one automatic one-way storage migration, taken after a
full export. We'll do it once the Python SDK officially supports 4.x, and it will need its own ADR
and a verification pass of the notes.
