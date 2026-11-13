---
applyTo: "**/*.surql,backend/app/db/**"
---

# SurrealQL & migration rules

- Target SurrealDB **3.3.x**. Syntax knowledge from 1.x/2.x may be outdated: check `docs/dev/surrealdb-notes.md` first; anything not marked ✅ must be verified against the dev DB (port 8100) and the result recorded there.
- Always bind parameters (`$user`, `$id`); never build queries with f-strings or concatenation.
- Shared dictionary rows have `owner = NONE`; user-created rows/edges have `owner = <user record>`. Every read of user-visible data filters `owner = NONE OR owner = $user`; writes to shared rows only happen in dictionary materialization code.
- Migrations: `backend/app/db/migrations/NNNN_snake_name.surql` (or `.py` with `async def up(db)` for data backfills). Forward-only; never edit a merged migration. Use `DEFINE ... IF NOT EXISTS` / `OVERWRITE` so a re-run is harmless.
- Tables are `SCHEMAFULL`; edges are `TYPE RELATION IN <from> OUT <to>`. Define indexes for every lookup used by a query; unique indexes for natural keys.
- After adding a migration: `./scripts/dev.ps1 test -Backend` regenerates/compares `backend/app/db/schema.snapshot.json` (commit the updated snapshot).
- Long or reused graph queries go in `backend/app/db/queries/<name>.surql`, loaded by name; short ones inline in repository functions.
