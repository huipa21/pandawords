# Import, export & backups

All archives are `.tar.gz` with a `manifest.json` at the root:

```json
{ "format": "pandawords.project", "version": 1, "app_version": "0.x.y",
  "created_at": "…", "lexicon_version": "…", "source_lang": "zh", "target_lang": "en",
  "attribution": ["Wiktionary (CC BY-SA)", "Open English WordNet (CC BY 4.0)", "ECDICT (MIT)"] }
```

## Availability and security scope

The project bundle import/export and user backup described below are **Phase 6 designs, not
implemented in this branch**. No cross-user isolation or archive-content test can be claimed for
those paths. The admin whole-site backup, scheduled backup and operator restore (task 6.1.5) are
implemented as described in [Admin site backup](#admin-site-backup-format-pandawordssite). There is
deliberately no browser or API site-restore upload. The production pre-migration SurrealDB export
remains a separate, database-only safety copy.

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
manifest.json  written first; format, version 1, app_version, created_at, trigger
               (manual|scheduled), lexicon_version, langs, attribution, database, media[]
db.surql       SurrealDB export (SDK `export_to`, HTTP /export); starts with `OPTION IMPORT;`
media/         full media volume (regular files only)
```

- **Integrity.** `manifest.database` records size, sha256, the SurrealDB server version and the
  row count of every table. `manifest.media` lists every media file with its size and sha256.
  The published archive also gets a sidecar `<archive>.sha256` (`sha256sum` format).
- **Excluded.** The lexicon (rebuilt or transferred separately; `lexicon_version` is recorded),
  `.env*`, `*.key`/`*.pem`/`*.p12`/`*.pfx`, symlinks, `*.partial` and restore/staging folders.
  The backup directory must not overlap the media or lexicon directories.
- **Publishing.** An archive is built in a `.work-*` folder, re-read and verified, then
  published by writing the sidecar and atomically renaming `.partial` to
  `site-<YYYYMMDDTHHMMSSffffff>Z.tar.gz`. Only archives with a sidecar are listed. Files are 0600
  and the directory is 0700. A file lock (`.site-backup.lock`, stale after
  `SITE_BACKUP_LOCK_STALE_SECONDS`) prevents concurrent backups and restores. Retention keeps the
  newest `SITE_BACKUP_RETAIN` complete archives and runs only after a successful publish, so a
  failed backup never deletes a valid earlier one.
- **On demand** (admin only, `require_admin`). These calls run in the API process:
  - `POST /api/admin/backups` starts a backup and returns `202`, or `409` when one is already
    running.
  - `GET /api/admin/backups` returns `{running, last_error, backups[]}`.
  - `GET /api/admin/backups/{name}` downloads an archive. The name is strictly validated, and
    unknown names return `404`.
- **Scheduled.** The `backup` compose service (same image, `python -m app.backup`) runs once a day
  at `SITE_BACKUP_TIME` (UTC). `python -m app.backup once` runs a single backup.
- **Restore.** The operator runs `bash restore.sh <archive>`; there is no browser or API path. The
  script checks the sidecar on the host, then works through these stages, each of which reports
  the stage name and exits non-zero on failure:
  1. **preflight** (`python -m app.backup check`): the archive is streamed and its manifest,
     paths, limits, sizes and checksums are validated. Unsafe paths, links or extra or missing
     entries are rejected.
  2. **stop**: `web`, `api`, `worker` and `backup` are stopped.
  3. **restore** (`python -m app.backup restore --replace`): the current database is saved as
     `pre-restore-<stamp>.surql` in the backup volume. The database is recreated empty,
     `db.surql` is imported, and the table counts are verified. Media are staged on the same
     volume, swapped in (with rollback if the swap fails) and verified against the manifest.
  4. **restart**: `docker compose up -d`, then the script waits for `/readyz`.

  Without `--replace`, the core refuses a non-empty target database and changes nothing.
