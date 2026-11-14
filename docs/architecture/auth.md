# Auth & users

- **Bootstrap**: on API startup, if no admin user exists, create one from `ADMIN_USERNAME` /
  `ADMIN_PASSWORD` with `must_change_password = true` in production.
- **No self-signup.** The admin creates users (username plus a temporary password). Users must change
  the password at first login.
- **Roles**: `admin` (user management, site backup) and `user`. Every user's data is isolated.
  Admins do not browse other users' learning data in the UI. They can only back up or restore the
  whole site.
- **Passwords**: argon2id via `pwdlib`. Minimum 10 characters.
- **Tokens**:
  - Access token: JWT (HS256, `JWT_SECRET`), 60 min, `sub` = user id, `role`. The client keeps it
    in memory only.
  - Refresh token: an opaque random 256-bit value sent as an httpOnly, Secure, SameSite=Strict
    cookie scoped to `/api/auth`. Only its SHA-256 hash is stored in `refresh_token`. It rotates on
    each use. Reusing a revoked token revokes the whole chain (theft detection).
- **Endpoints**: `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout`,
  `GET /api/auth/me`, `POST /api/auth/password`. Admin: `GET/POST /api/admin/users`,
  `PATCH /api/admin/users/{id}` (disable, role, reset password).
- **Database access**: the backend connects to SurrealDB with one database-level user, and all
  authorization is done in Python (see ADR 0006). SurrealDB record-level permissions are not used.
- **Login protection**: exponential backoff per username + IP (in-process, since there is a single
  API instance). Generic error messages.

## Security core (1.5.2)

- `services.auth.login(db, settings, username, password)` and
  `refresh(db, settings, token)` return internal `AuthTokens` (user, access token, refresh token).
  `logout(db, token)` revokes that refresh family and is idempotent for a well-formed token.
  Tokens/passwords/hashes are excluded from model representations; services never log them.
  API response models must **not** serialize the internal `User.password_hash`.
- Access claims are strictly validated: pinned HS256, required `sub`/`role`/`iat`/`exp`, integer
  timestamps (not bool/string/float), valid chronology, expiry and not-in-the-future issuance,
  and only the two supported roles. `JWT_ACCESS_TTL_MINUTES` defaults to **60**, matching
  `.env.example`; an existing private environment override is respected.
- JWT `sub` and internal `User.id` are the API `rid`: unpadded canonical base64url of
  `user:<scalar-key>`, never a raw SurrealDB ID. The small typed `domain.identity` helpers
  support user IDs only. General record parsing, array IDs and deterministic dictionary keys
  remain task 2.2.2; that task can extend/reuse this contract without changing auth subjects.
- Refresh rotation and reuse revocation run in server transactions with bounded retries for
  structured transaction-conflict errors. Existing `replaced_by` links identify the connected
  family in both directions. All family reads/writes bind the credential's user; replaying
  any ancestor revokes every descendant, but not a separate login or another user's sessions.
  Raw refresh values are random 32-byte URL-safe tokens; only SHA-256 hashes reach the DB.
  Revocation commits before a generic authentication error is raised. Retain revoked ancestors
  while their family has a live descendant; deleting them prematurely loses theft detection.
- Bootstrap validates a non-placeholder signing secret of at least 32 bytes. When no admin
  exists it requires configured credentials (password minimum 10), then transactionally creates
  one admin using a stable bootstrap record ID. Repeated/concurrent startup does not reset
  the password. Production sets `must_change_password = true`. Existing admins mean bootstrap
  credentials are no longer required, but a valid JWT secret still is.
- Startup waits a bounded time for initial DB connectivity and bootstrap. Bootstrap errors
  during that wait fail startup explicitly. A DB outage preserves `/healthz` and offline OpenAPI,
  but `/readyz` stays unavailable until connection **and bootstrap** succeed; late bootstrap
  failure is logged by exception type only and keeps auth readiness closed. There is no
  anonymous-auth fallback. Creating OpenAPI does not construct a DB connection or bootstrap.
- Transaction begin/rollback cleanup is cancellation-shielded. Cleanup failures log only their
  exception type; the original error still propagates. Structured conflicts retry in a fresh
  transaction even when the server already aborted the old one and rejects its cancellation.
- Cookie handling, endpoint/public response models, auth dependencies, forced-password gate and
  login backoff belong to task **1.5.3**; this core does not register new endpoints.
