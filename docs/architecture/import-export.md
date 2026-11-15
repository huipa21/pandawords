# Import, export & backups

All archives are `.tar.gz` with a `manifest.json` as the **first** member:

```json
{ "format": "pandawords.project", "version": 1, "schema_revision": 1, "app_version": "0.x.y",
  "created_at": "2026-01-02T03:04:05.000000Z", "lexicon_version": "…", "source_lang": "zh",
  "target_lang": "en", "source": "<64 hex or null>",
  "attribution": ["Wiktionary (CC BY-SA)", "Open English WordNet (CC BY 4.0)", "ECDICT (MIT)"],
  "entries": [{ "path": "data.json", "sha256": "<64 hex>", "size": 1234 }, …] }
```

## Bundle contract (6.1.1)

Implemented in `backend/app/domain/bundle*.py` (pure models/validation) and
`backend/app/services/bundle_archive.py` / `bundle_io.py` (archive I/O).

**Compatibility rules**

| Field | Rule |
|---|---|
| `format` | `pandawords.project`, `pandawords.user` or `pandawords.site`; callers pass the formats they accept and anything else fails with `bundle.unexpected_format`. `data.json` never declares `pandawords.site`. |
| `version` | Major format version (currently `1`). Any other value fails with `bundle.unsupported_version` **before any other member is extracted** and before any database/media write. |
| `schema_revision` | Additive revision of `data.json` within the major (currently `1`). Newer revisions fail with `bundle.unsupported_schema`, because this reader would silently drop unknown fields; older revisions of the same major stay readable. `data.json` repeats it and must match. |
| `app_version`, `lexicon_version` | Informational. Differences never block an import (shared rows travel in the bundle and existing shared rows are never overwritten); `compatibility_warnings()` reports them, plus source/target language differences from the importer, for the result screen. |
| `source_lang`, `target_lang` | BCP-47-like tags (letters/digits/hyphens). |
| `source` | Optional, non-identifying source fingerprint written by project export: HMAC-SHA256 keyed by a key derived from `JWT_SECRET` over the exporting user's key and the `data.json` sha256. Only this server can check it, it is bound to the content (any edit of `data.json` breaks it) and differs per bundle, so it does not link bundles to an account for anyone else. Rotating `JWT_SECRET` makes old bundles count as foreign (progress then defaults to off). |
| `attribution` | Required (non-empty) when the bundle contains shared dictionary rows. |
| `entries` | Integrity list: path, sha256, size for every member except the manifest; no duplicates, and the archive must contain exactly these members. |

**Archive safety** (`read_archive`): one streaming pass; only regular files with safe relative
names (no absolute/drive paths, backslashes, `.`/`..` segments, links, devices or directories);
bounded entry count, per-entry size, total expanded size and compressed size
(`ArchiveLimits`); each member's size and sha256 must match the manifest. Members are extracted
with exclusive creates into a private staging directory that is removed on any failure or
`close()`. Writing (`write_archive`) puts `manifest.json` first and other members sorted with
fixed metadata (mtime 0, uid/gid 0), streams media from disk, validates the result with the
reader's rules, and publishes by atomic rename of a hidden temporary file in the destination
directory; failures leave no partial archive.

**`data.json`** (`BundleData`, JSON Schema `backend/app/domain/bundle.schema.json`, generated
from the pydantic models with `uv run python -m app.domain.bundle`; a unit test fails on
drift). Top-level keys: `format`, `schema_revision`, `records` (dictionary rows, discriminated
by `table`), `edges` (the nine dictionary relations, discriminated by `table`), `projects`,
`includes` (`hidden`, `added_at`, optional `study_order`), `overrides` (target + partial
`fields` + `updated_at`), `notes`, `media`, `memory` (sense + FSRS `card` + `introduced`),
`review_log`, and `preferences` (`pandawords.user` only: theme, locale, accent,
desired retention, review media toggles, source/target language). Unknown fields, wrong types
and booleans-as-integers are rejected (strict mode).

**References.** Every row is identified by a `ref`, and every relation uses refs:

- Shared dictionary rows (`owner: "shared"`, database `owner = NONE`) use their deterministic
  identity, `<table>:<canonical JSON key>`, e.g. `lemma:["en","run"]`. Shared edges carry
  `identity` (the trailing components of their deterministic ID `[from, to, *identity]`) so an
  importer can merge them by ID.
- Owner-owned rows (`owner: "owned"`) and shared media (whose IDs are random) use bundle-local
  refs `<table>:@<n>`, numbered per table in the sorted order of their source IDs. Database IDs
  of user-owned rows, the user ID and other accounts' IDs never appear in a bundle.
- `review_log.project` is `null` when the original project is not part of the bundle (deleted or
  another project); its memory is identified by `sense`.

**Never serialized:** user account fields (username, password hash, role, flags), refresh
tokens, secrets/configuration, media storage `path` (media bytes live at content-addressed
`media/<sha256><ext>`), project `srs_revision`, user `tag_revision`, review-log
`request_fingerprint` and `receipt` (both embed source database IDs; the receipt's resulting
card is kept as `card_after` so an importer can rebuild a receipt). Serialization rejects any
row, edge or media owned by another account (`bundle.foreign_owner`).

**Validation order** (`load_bundle`): archive safety and integrity → manifest/version →
`data.json` schema → cross-record checks (`validate_bundle`): unique refs; ref form matches
owner scope; edge endpoint tables, existing endpoints, shared edges only between shared
endpoints, no `identity` on owned edges, phrase-only `contains`/`used_in` lemma endpoints,
no self `relates_to`/`member_of`, no duplicate edges; memberships only to existing projects and
lemma/lexeme/sense/sentence/passage; one override per target without `id`/`owner`/`in`/`out`
keys; note targets exist; one memory per sense; logs reference bundled memory and project;
unique attempt IDs; media kind/MIME/extension agreement, audio-only accent, shared media only as
audio for shared targets, every media file present and no unreferenced media files. Project
bundles contain exactly one project and no preferences. Errors are `BundleError`
(`bundle.<reason>`, HTTP 422) with a `stage` (`archive`, `manifest`, `data`, `references`,
`media`) and short path-free `problems`.

**Deterministic output.** Collections are sorted canonically (records by table/ref, edges by
table/endpoints/content, memberships by project/target, logs by time/attempt); list values
inside a row (forms, pronunciations, examples) keep their stored order. JSON uses sorted keys
and UTC timestamps with microseconds, so the same logical input produces byte-identical
`data.json` and, with the same `created_at`, byte-identical archives.
## Availability and security scope

The bundle contract, validator and archive helpers (6.1.1), project **export** (6.1.2) and
project **import** (6.1.3, below) are implemented. User backup/restore described below is a
**Phase 6 design, not implemented in this branch**; no cross-user isolation or archive-content
test can be claimed for that path. The admin whole-site backup, scheduled backup and operator restore (task 6.1.5)
are implemented as described in [Admin site backup](#admin-site-backup-format-pandawordssite).
There is deliberately no browser or API site-restore upload. The production pre-migration
SurrealDB export remains a separate, database-only safety copy.

## Project bundle (`format: pandawords.project`)

```
manifest.json
data.json      dictionary subset (lemmas, lexemes, senses, edges), user-owned items,
               project + includes (with hidden), overrides, notes, memory, review_log
media/         images and audio referenced by data.json
```

- **Export** (6.1.2): `GET /api/projects/{id}/export` (authenticated owner; another user's or a
  missing project is 404) streams `<project name>.pandawords-project.tar.gz`
  (`application/gzip`, `Cache-Control: no-store`). Implementation:
  `app/db/project_export.py::load_project(db, owner, project) -> BundleSource` reads one
  transaction-consistent, owner-filtered snapshot; `app/services/project_export.py::
  export_project(db, settings, owner, project_id) -> ProjectArchive` hashes media, serializes
  with `serialize_bundle` and writes with `export_bundle`. Contents:
  - the project and its `includes` (all of them, hidden ones too, with `hidden`, `added_at`,
    `study_order`; duplicate legacy memberships of one target merge, hidden wins);
  - dictionary rows (shared and the owner's) reached from membership targets: a sense's lexeme
    and lemma, a lemma's lexemes, then outgoing `composed_of` → morphemes, `member_of` → tags
    (and parent tags), `used_in` → sentences/passages/phrase lemmas and `part_of` → passages,
    to a fixed point (≤ 12 rounds); senses come only from memberships, so `has_sense` edges are
    kept only to selected senses. Every visible edge (shared or the owner's, both endpoints
    visible) between two exported records is included (`relates_to`, `derives_to`, `contains`
    too);
  - the owner's overrides of exported records, notes on exported records or the project,
    memory of the selected (membership) senses and all of the owner's review logs of that
    memory (logs from other projects get `project: null`);
  - media targeting exported records plus pronunciation audio they reference: the owner's media
    and shared audio. Files are read from `MEDIA_DIR` through the protected-path resolver and
    stored as `media/<sha256><ext>`. Missing, unreadable, non-file or unsafe-path files are
    skipped (their rows dropped, pronunciation `audio` set to `null`), logged without paths and
    counted in the `X-PandaWords-Skipped-Media` response header.
  - The manifest uses the project's source/target language, `app_version`, and the dictionary
    attribution when shared rows are present.
  - Bounds: 10,000 memberships, 25,000 records, 100,000 traversed edges, 50,000 notes/media,
    200,000 review logs, archive limits from `ArchiveLimits`; exceeding them is
    `project.export_too_large` (413), never a truncated archive.
  - The archive is built off the event loop in a fresh private directory under
    `BUNDLE_WORK_DIR` (default: system temp), validated and atomically published by
    `export_bundle`, streamed with `FileResponse`, and the directory is removed after sending,
    on client disconnect, and on any failure. Only the (bounded) `data.json` is held in memory;
    media is hashed and archived by streaming from disk. Database IDs, storage paths and
    credentials never appear in the archive.
- **Import** (6.1.3): `POST /api/projects/import[?include_progress=true|false]`, authenticated,
  raw request body `application/gzip` (not multipart, so nothing is spooled before the bound).
  The body is streamed into a private directory under `BUNDLE_WORK_DIR` and rejected with
  `bundle.too_large` (413, stage `upload`) above `BUNDLE_IMPORT_MAX_BYTES` (default 512 MiB;
  a larger `Content-Length` is refused up front); the directory is removed afterwards whatever
  happens. Response `201` `ImportSummary`:
  `{project_ids: [id], progress_imported, same_source, created: {kind: n}, merged: {kind: n},
  skipped: {kind: n}, conflicts: [notice], warnings: [compatibility warning]}`.
  - **Validate everything first**: `load_bundle` (archive safety, manifest, `data.json`,
    references), then ≤ 500,000 items, then every media file (non-empty; images ≤ 10 MiB and
    decodable as their declared type via `image_validation`; audio ≤ `AUDIO_MAX_BYTES` with a
    magic-byte check for its MIME). Failures are `bundle.<reason>` (422) with `stage` and
    path-free `problems` in the error body; nothing is written.
  - **Shared items** merge by deterministic ID. Missing ones are created as shared
    (`owner = NONE`) from the validated bundle data; existing ones are never modified (missing
    shared edges likewise). New shared lexemes get `pron.audio = null`, so user files never
    become shared rows. A shared ref/edge ID that is occupied by a **non-shared** row (a forged
    ref at another user's record) fails with `bundle.identity_conflict` (409, problem
    `shared_identity: <table>`) without revealing the row.
  - **User-owned items** (records, edges, project, memberships, notes, media) get fresh IDs owned
    by the importer and every reference is remapped. Edge endpoints are only verified shared
    IDs, fresh owned IDs or reused visible lemmas, so no edge can reach another user's rows.
    Memberships keep `hidden`, `added_at` and `study_order`; the project keeps its name,
    languages, plan and `created_at`. An owned lemma whose `(lang, text)` already exists as a
    shared lemma or the importer's own is **reused** (counted in `merged`); if another user owns
    it (`lemma_lang_text` is globally unique) the import fails with 409 `lemma_identity: lemma`.
  - **Media**: bundle media is stored as the importer's own (also formerly shared audio, unless
    its shared target already exists, then it is skipped) under a fresh `{kind}/{id}{ext}`.
    Owned lexeme pronunciation audio is remapped to the imported media.
  - **Overlays**: overrides are validated like the API (`OverrideFields`, editable fields) and
    created for the importer; an existing override of the same target is kept
    (`override_kept`). Notes are copied.
  - **Progress** (`include_progress`): default **on only for a verified same-user restore**
    (`same_source`: the manifest `source` HMAC matches this user and this `data.json`), off
    otherwise; an explicit query value wins. A sense that already has the importer's memory keeps
    it untouched, together with the importer's history (`memory_kept`; the bundle's logs of that
    sense are skipped). On: cards and review logs are imported; logs whose `attempt_id` the
    importer already has are skipped (`review_log_duplicate`), so completion receipts are never
    duplicated; a log with `project: null` is attributed to the imported project; when
    `card_after` is present the completion receipt is rebuilt for the new IDs (its
    `request_fingerprint` is derived from the imported receipt, so the optimizer can use it but it
    never matches a client's original request fingerprint). Off: each memory entry
    becomes a new card (`introduced = false`, default FSRS state) and no logs are imported.
  - **Repeated imports** are safe and create **another project copy each time** (fresh owned
    IDs); shared rows/edges merge idempotently, memory/history are not duplicated.
  - **Atomicity**: all rows are written in one SurrealDB transaction (`INSERT` with explicit
    IDs, then `INSERT RELATION`, then review logs; `member_of` imports bump
    `user.tag_revision`). Media files are copied with exclusive creates before commit and
    removed if anything fails, including commit and transaction-conflict retries. Unexpected
    database/file failures are `bundle.apply_failed` (500, stage `apply`, no details); a failed
    import leaves no rows, memberships or media files.
  - **Reusable core for user restore (6.1.4)**: `app/domain/bundle_import.py`
    (`ImportOptions`, `allocate`, `state_query`, `ExistingState`, `ImportPlan`,
    `ImportSummary`, `check_size`), `app/domain/bundle_import_plan.py::build_plan`,
    `app/db/bundle_import.py` (`read_state`, `write_plan`) and
    `app/services/bundle_import.py::apply_bundle(db, settings, owner, bundle, options)`
    (+ `validate_media_files`); `app/services/project_import.py` only adds the upload, format
    and summary handling.
  - Known limits: tag-hierarchy cycle checks are not re-run for imported `member_of` edges
    (imported tags are fresh, so only edges to shared tags matter); creating missing shared rows
    from a bundle trusts its validated content (the dictionary may gain rows from another
    instance).
- The JSON Schema for `data.json` lives at `backend/app/domain/bundle.schema.json` and is
  enforced on import (see Bundle contract above).

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
