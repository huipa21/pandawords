# 0010 — Forward-only migrations

**Status:** Accepted (2026-11-13)

**Decision.**
- Migrations live in `backend/app/db/migrations/NNNN_name.surql`, or `.py` with `async def up(db)`
  for data backfills.
- Applied versions are tracked in `_migration` (version, name, checksum, applied_at). The checksum
  catches edits to applied files.
- Each file runs in a transaction (to be verified, N16). Statements are idempotent
  (`IF NOT EXISTS` / `OVERWRITE`).
- In production a one-shot `migrate` compose service runs them. It takes a site export first, and
  `api`/`worker` wait for it to finish. In development, `dev.ps1 up` runs them.
- There are no down-migrations. Rollback is a restore from the pre-migration export.
- `schema.snapshot.json` (from `INFO FOR DB`) is committed and checked by a drift test.

**Consequences.** There is exactly one migrator, so nothing races. Every schema change is reviewable
as a diff in one file.
