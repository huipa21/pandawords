# Auth & users

## Offline device data (7.1.2)

Offline review IndexedDB is partitioned by authenticated user ID, capped at 20
entries and contains no credentials or private grader keys. Explicit logout or
credential rejection invalidates in-flight client writes synchronously, then
deletes that owner's data before a queued login can complete. A transient refresh
outage hides/revokes access to the queue without deleting unsynced answers; a
successful same-user refresh restores access. Account replacement purges the prior
owner; BroadcastChannel invalidates open offline views in other tabs. Deletion
failure logs only `offline_review_purge_failed` and shows a localized warning
to clear site data before sharing a device. No auth token is persisted to enable
cold-start offline login; existing network-backed guards remain in force.

- **Bootstrap**: on API startup, if no admin user exists, create one from `ADMIN_USERNAME` /
  `ADMIN_PASSWORD` with `must_change_password = true` in production.
- **No self-signup.** The admin submits a username and optional role; the API generates a random
  temporary password. Admin-created accounts must change it at first login in every environment.
- **Roles**: `admin` (user management) and `user`. Every user's learning data is isolated,
  including from admins. Site backup/restore is planned but is not implemented on this branch.
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
- **Admin account contract (1.5.4):** list accepts `page` (default 1) and `page_size`
  (default 20, maximum 100), returning `{items, total, page, page_size}` ordered by username/id.
  Create accepts `{username, role?}` and returns 201 `{user, temporary_password}`. Patch accepts
  `{disabled?, role?, reset_password?: boolean}`; reset generates a new password and sets
  `must_change_password`, returning the same envelope (`temporary_password` is null otherwise).
  Extra fields and explicit null changes are rejected. Reads project only `UserRead` fields;
  credential hashes and other users' learning data are never exposed. Admin responses use
  `Cache-Control: no-store`; deliver temporary passwords securely, never log or persist them.
  Unknown users return 404 and duplicate usernames return 409.
- **Admin safety:** no self-disable/self-demotion, and no removal of the last **enabled** admin.
  Disabled admins do not count and cannot act, even with a stale access token. Each mutation
  increments the internal `admin_guard:singleton.version` in the same transaction before
  rechecking the acting admin and target; transaction conflicts retry the entire check.
  This serializes concurrent two-admin disables/demotions rather than allowing write skew.
  Disable/enable, effective role changes and password resets revoke the target's refresh
  sessions in the same transaction. Existing access tokens are checked against current DB
  identity/role/disabled/password-change state; no admin privilege bypasses owner filtering.
- **Database access**: the backend connects to SurrealDB with one database-level user, and all
  authorization is done in Python (see ADR 0006). SurrealDB record-level permissions are not used.
- **Login protection**: exponential backoff per username + IP (in-process, since there is a single
  API instance). Generic error messages.

## Admission control and privacy (7.1.3)

The API uses bounded, process-local fixed windows starting at the first request. Defaults per
60 seconds are 30 authentication operations per client IP, 60 anonymous requests per client IP,
600 requests per signed user, and 120 expensive operations per identity. Login/refresh always
spend the anonymous IP budget, even with a bearer token; login/refresh/password also spend the
authentication IP budget. Invalid or expired tokens are anonymous for budgeting; a valid JWT's
subject identifies the user bucket, but authorization still reloads current database state.
All writes and bounded costly reads (graph, dictionary, content, images, media, relations, tag
assignments, dashboard, project tree and study plan) spend the expensive budget. Health/readiness
are exempt. Limits, window and 16,384-entry capacity are configurable in `.env.example`.
At capacity, new identities fail closed rather than evicting an active restriction. A restart
clears these in-memory windows; keep **one API worker and one replica** unless admission control
is moved to a shared store. Login backoff remains separately bounded.

The immediate peer is the client address unless it belongs to `TRUSTED_PROXY_CIDRS`. Only one
valid `X-Forwarded-For` IP from that peer is accepted; duplicate, chained, malformed or scoped
IPv6 values are ignored and IPv4-mapped IPv6 is canonicalized. A trusted proxy can also set one
valid `X-Forwarded-Proto` value; other peers cannot influence the request scheme. The proxy must
overwrite both headers, not append client-supplied values. The same canonical IP feeds login
backoff. Production trusts only the web container's fixed `/32`; the web container trusts only
an explicitly configured Caddy address as described in [deployment.md](../dev/deployment.md).

Rate rejections use the standard `{code, message, field}` envelope, `Retry-After` seconds
(rounded up, at least one), and `Cache-Control: no-store`; Pixabay cooldown and full-queue 429s
also include retry guidance. Rate-limit logs contain only the category, never an identity or
request content. HTTP client/provider library logs and web/API access logs are disabled because
URLs can carry credentials or private queries; operators must not re-enable such logging without
equivalent redaction. Tests use synthetic secrets only.

## Security core (1.5.2)

If JWT configuration is unavailable, the admission limiter logs the fixed
`rate_limit_token_identity_unavailable` event and charges requests to the anonymous
budget. It does not interpret bearer identities or bypass endpoint authentication;
private routes and readiness retain their existing auth-configuration failures.
Public diagnostic endpoints can still run and report their own failures.

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
- The core remains usable independently; HTTP contracts are documented below.

## Auth API (1.5.3)

| Endpoint | Input | Success |
|---|---|---|
| `POST /api/auth/login` | JSON `{username, password}` | Auth response and refresh cookie |
| `POST /api/auth/refresh` | Refresh cookie; no request body | Auth response and rotated cookie |
| `GET /api/auth/me` | Bearer access token | Public user |
| `POST /api/auth/password` | Bearer token; JSON `{current_password, new_password}` | Auth response and new cookie |
| `POST /api/auth/logout` | Bearer token; optional refresh cookie | 204, cookie cleared |

- An auth response is `{access_token, token_type: "bearer", user}`. The public user contains
  `id` (the canonical API rid), `username`, `role`, `disabled`, `must_change_password`,
  `source_lang`, `target_lang`, and `prefs` (`theme`, `locale`, `accent`). Neither password hashes
  nor refresh tokens appear in JSON. Success responses are `Cache-Control: no-store`.
- Cookie name: `refresh_token`; httpOnly, `SameSite=Strict`, path `/api/auth`, `Secure` in
  production. Its maximum age matches `JWT_REFRESH_TTL_DAYS`. Refresh failures clear the
  cookie and retain the standard `{code, message, field}` error envelope.
- `current_user` decodes the access JWT and reloads the enabled user on every request.
  `require_admin` checks the current database role, not the potentially stale JWT role.
  Missing/invalid credentials and disabled/unknown users fail with generic 401
  `auth.invalid_credentials`; non-admin authorization fails with 403 `auth.forbidden`.
- A user with `must_change_password` can authenticate through public login but may only call
  authenticated `me`, `password`, and `logout`. Other authenticated routes, **including
  cookie-based refresh**, return 403 `auth.password_change_required`. Refresh does not rotate
  the session in this case and clears the cookie. A reloaded frontend must fall back to login,
  then route the user to password change; it must not rely on refresh bypassing the gate.
- Password change verifies the current password and requires a new password of 10–1024
  characters. One owner-scoped transaction compares the verified password hash, updates the
  password, clears the forced-change flag, revokes **all** old refresh sessions, and creates a
  fresh refresh session. The response gives a usable new access token. Existing access JWTs
  retain their configured lifetime; user state/role are still reloaded on every request.
  Login rechecks the verified hash when issuing its session, preventing a concurrent password
  change from allowing a stale-password login. Logout revokes only a cookie family belonging
  to the authenticated user; a foreign user's cookie is cleared locally but not revoked.
- Login protection is per application process, keyed by the username and canonical trusted-client
  IP (or direct transport IP when no proxy is trusted). Failed credentials impose 1, 2, 4, … up to 60
  seconds of backoff; early/concurrent retries return generic 429 `auth.login_throttled`.
  Success resets the counter. State expires after 15 minutes and is capped at 4096 hashed
  keys; a full active map rejects new attempts rather than evicting live restrictions.
  It is deliberately not a distributed limiter: deployment requires a single API process.
