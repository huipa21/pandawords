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
