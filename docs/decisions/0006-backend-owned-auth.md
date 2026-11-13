# 0006 — Auth and authorization in FastAPI

**Status:** Accepted (2026-11-13)

**Context.** SurrealDB offers record-level access methods and table permissions, but its 3.x syntax
is less familiar, and the app needs custom flows (admin-created users, forced password change,
refresh rotation).

**Decision.** FastAPI owns authentication (argon2id, JWT access token, rotating opaque refresh
token) and authorization (owner checks in repositories). The backend connects to SurrealDB as one
database-level user.

**Consequences.** Simpler, testable in Python. Every repository function must enforce ownership, and
isolation tests are mandatory. SurrealDB is never exposed to clients.
