# 0010 — Forward-only migrations

**Status:** Accepted (2026-11-13)

**Decision.**
- Migrations live in `backend/app/db/migrations/NNNN_name.surql`, or `.py` with `async def up(db)`
  for data backfills.
- Applied versions are tracked in `_migration` (version, name, checksum, applied_at). The checksum
  catches edits to applied files.
- Each file and its history record run in one UUID transaction (`begin`, `txn_id`,
  `commit`/`cancel`), verified by N16/N17 and runner integration tests. Every raw statement
  status is checked; an ERR cannot silently become an applied migration. Statements are
  idempotent (`IF NOT EXISTS` / `OVERWRITE`).
- In production a one-shot `migrate` compose service runs them. It takes a site export first, and
  `api`/`worker` wait for it to finish. In development, `dev.ps1 up` runs them.
- There are no down-migrations. Rollback is a restore from the pre-migration export.
- `schema.snapshot.json` (from `INFO FOR DB`) is committed and checked by a drift test.

**Consequences.** There is exactly one migrator, so nothing races. Every schema change is reviewable
as a diff in one file.

**Runner (1.3.3).** From `backend`, run `python -m app.db.migrate`, or add `--dry-run` to
validate history and list pending files without creating history/schema. Connection settings
come from the existing `Settings` / `.env.dev`; tests use only port 8101 and random databases,
removed by exact bound name. The runner creates the `_migration` schema before the first
file. `0001_bootstrap.surql` reserves that history table; application schema follows later.
Versions must be unique across both extensions. SHA256 covers the exact file bytes; edited,
renamed, or missing applied files fail before pending files execute. A failed file rolls
back its schema, data and marker; earlier successful files remain applied.

Python backfills define `async def up(db: MigrationConnection) -> None`, importing
`MigrationConnection` from `app.db.migration_store`. Only `await db.query(sql, variables)`
is exposed: all calls use the same runner-owned transaction, and query results are a list
with one result per statement. Do not start/commit transactions or open another connection.
Even caught query failures prevent commit. Python files execute from their checksummed
bytes, not cached bytecode. CLI failures exit nonzero. Snapshot/drift tooling remains 1.3.4;
aggregate `dev.ps1` commands remain 1.6.1.
