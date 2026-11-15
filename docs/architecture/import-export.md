# Import, export & backups

All archives are `.tar.gz` with a `manifest.json` as the **first** member:

```json
{ "format": "pandawords.project", "version": 1, "schema_revision": 1, "app_version": "0.x.y",
  "created_at": "2026-01-02T03:04:05.000000Z", "lexicon_version": "…", "source_lang": "zh",
  "target_lang": "en",
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

The project bundle import/export, user backup, whole-site backup, scheduled backup and restore
APIs described below are **Phase 6 designs, not implemented in this branch**; only the bundle
contract, validator and archive helpers above (6.1.1) exist. No cross-user
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
- The JSON Schema for `data.json` lives at `backend/app/domain/bundle.schema.json` and is
  enforced on import (see Bundle contract above).

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
