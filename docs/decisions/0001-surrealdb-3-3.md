# 0001 — SurrealDB 3.3.x now, 4.x later

**Status:** Accepted (2026-11-13)

**Context.** SurrealDB 4.0 was released in early November 2026. It introduces a new protocol,
replaces RocksDB with SurrealKV, and the upgrade is one-way. The Python SDK `surrealdb` 3.0.0
(released 2026-11-04) documents server v3.3.0+ features and doesn't claim 4.0 support. The AI
agent's knowledge of 3.x/4.x SurrealQL is limited.

**Decision.** Use SurrealDB **3.3.x** (pinned patch, RocksDB storage) with SDK 3.0.x. Keep all
SurrealQL in `backend/app/db/`. Verify syntax against a real server and record it in
`docs/dev/surrealdb-notes.md`.

**Consequences.** Upgrading to 4.x later means one automatic one-way storage migration, taken after a
full export. We'll do it once the Python SDK officially supports 4.x, and it will need its own ADR
and a verification pass of the notes.
