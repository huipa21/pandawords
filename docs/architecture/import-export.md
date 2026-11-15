# Import, export & backups

All archives are `.tar.gz` with a `manifest.json` at the root:

```json
{ "format": "pandawords.project", "version": 1, "app_version": "0.x.y",
  "created_at": "…", "lexicon_version": "…", "source_lang": "zh", "target_lang": "en",
  "attribution": ["Wiktionary (CC BY-SA)", "Open English WordNet (CC BY 4.0)", "ECDICT (MIT)"] }
```

## Availability and security scope

The project bundle import/export, user backup, whole-site backup, scheduled backup and restore
APIs described below are **Phase 6 designs, not implemented in this branch**. No cross-user
isolation or archive-content test can be claimed for unavailable paths. The existing production
pre-migration SurrealDB export is database-only: it does not include media and is not a tested
whole-site backup or restore. Reaudit ownership, archive validation and privacy when Phase 6 is
integrated; do not rely on the proposed features until then.

## Project bundle (`format: pandawords.project`)

```
manifest.json
data.json      dictionary subset (lemmas, lexemes, senses, edges), user-owned items,
               project + includes (with hidden), overrides, notes, memory, review_log
media/         images and audio referenced by data.json
```

- **Export** includes everything, review progress too.
- **Import**:
  - Shared dictionary items are merged by deterministic ID. Missing ones are created as shared
    (`owner = NONE`), and existing ones are not modified.
  - User-owned items get new IDs owned by the importer, and references are remapped.
  - Overrides are applied to the importer.
  - Option **Import progress**: on by default when the bundle came from the same user (a restore),
    off otherwise. When it's off, memory rows start as new cards.
  - Senses that already have a memory row for the importer: keep the importer's existing memory
    (never overwrite).
- A JSON Schema for `data.json` lives at `backend/app/domain/bundle.schema.json` and is validated
  on import.

## User backup (`format: pandawords.user`)

The same as a project bundle, but covering all of the user's projects, all user-owned items, notes,
media, memory, review logs and preferences. Restore works like import with progress always on.

## Admin site backup (`format: pandawords.site`)

```
manifest.json
db.surql       output of `surreal export` (via the HTTP /export endpoint or the CLI in the surrealdb container)
media/         full media volume
```

- Created on demand from `/admin/backup`, and on a schedule by the `backup` compose service
  (daily, keeps the last N). It also runs automatically before migrations in production.
- Restore: `deploy/restore.sh <archive>` stops api/worker, imports `db.surql` into an empty database,
  restores media, then starts the services again. The lexicon is **not** included because it is
  rebuilt or transferred separately. The manifest records `lexicon_version`.
