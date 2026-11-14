# Phase 6 - Import/export & backups: task details

The format for each task is Goal, Deliverables, Acceptance and Docs. Dependencies, waves and
status are in [PLAN.md](PLAN.md); a task may start as soon as its own dependencies are complete.
Read [import-export.md](../architecture/import-export.md),
[data-model.md](../architecture/data-model.md), [auth.md](../architecture/auth.md),
[deployment.md](../dev/deployment.md) and [testing.md](../dev/testing.md) for existing contracts.

## Dependencies and parallel execution

- **6.1.1** (bundle format/schema/serializers) and **6.1.5** (site backup/restore) are independent
  first-wave tasks. Both may start when their PLAN dependencies are ✅.
- **6.1.2** depends on 6.1.1; **6.1.3** depends on 6.1.2; **6.1.4** depends on 6.1.3.
  **6.1.6** waits for 6.1.2–6.1.5.
- Use one coordinator for the phase: only that coordinator edits [PLAN.md](PLAN.md) and
  [PROGRESS.md](PROGRESS.md) on `main`, assigns task worktrees, and serializes merges and
  generated-artifact updates. Parallel tasks need disjoint file scopes; archive schema,
  serializer and deployment changes must not overwrite one another.
- Recheck dependencies and worktree status at launch. Use isolated databases and media directories
  for tests. Never use real user archives or production backups as test fixtures.

## Shared implementation rules

- Keep the three formats distinct: `pandawords.project` for one project,
  `pandawords.user` for one user's complete data, and `pandawords.site` for an operator's full
  database/media backup. Follow [import-export.md](../architecture/import-export.md) as the
  architecture contract; update it if implementation details change.
- Shared dictionary records merge by deterministic identity and are never overwritten by an
  import. User-owned records and edges are imported for the authenticated owner with all
  references remapped. Independently validate record, edge and endpoint ownership.
- Validate archive format, version, schema, sizes, counts, references and media before applying
  changes. Reject unsafe paths, traversal, unsupported entries, malformed archives and unknown
  incompatible versions explicitly. Do not expose local storage paths or include credentials,
  refresh tokens, secrets or server configuration in user bundles.
- Bound memory, archive entry count, expanded size and import/export duration; stream large media
  where practical. Do not publish a partial archive or leave partially imported database rows or
  files after a failed operation. Errors and completion results must identify the failed stage
  without disclosing private data.
- User export/import and user restore are authenticated and owner-scoped. Site backup/restore is
  an administrator/operator capability and must not be reachable as an ordinary user import.
- Preserve protected media delivery. User bundles carry referenced media bytes, not provider
  hotlinks or filesystem paths. Site backups include the media volume; the separately rebuilt
  lexicon is not part of a site backup.
- Use forward-only migrations if a concrete new schema requirement is found. Generated API types,
  schema snapshots and migration versions are centrally regenerated/allocated from the integrated
  tree.

## 6.1 Bundle format and serializers

### 6.1.1 Versioned bundle contract, JSON Schema and serializers
- **Goal:** define a validated, versioned interchange contract that project export/import and user
  backup/restore can share without losing graph relationships or ownership semantics.
- **Deliverables:**
  - Implement the documented `.tar.gz` envelope with a root `manifest.json`, structured data and
    referenced media. Keep the public format identifiers and manifest concepts in
    [import-export.md](../architecture/import-export.md); add compatibility rules for format and
    schema versions, application/lexicon versions, languages, source attribution and integrity
    metadata.
  - Maintain the JSON Schema at `backend/app/domain/bundle.schema.json` and typed serializers for
    every supported record/edge category. Represent IDs and references consistently, preserve
    optional fields and ordering, and distinguish shared dictionary data from owner-owned data.
  - Define deterministic serialization and stable bundle-local references so import can validate
    referential integrity and remap user-owned records without exposing another account's IDs.
    Never serialize credentials, auth tokens, server secrets or filesystem paths.
  - Validate schema and cross-record relationships before database/file mutation. Report
    unsupported major versions and malformed or incompatible data explicitly.
- **Acceptance:**
  - Round-trip fixtures cover all supported dictionary records/edges, user-created content,
    project membership/hidden state, overrides, notes, review progress, preferences where the
    format includes them, and media references.
  - Schema tests accept valid current bundles and reject missing required fields, wrong types,
    invalid versions, dangling references, unsupported owner/edge combinations and unsafe media
    metadata.
  - Repeated serialization of the same logical input produces stable data and references; unknown
    incompatible versions fail before any database or media writes.
- **Docs:** import-export.md, data-model.md, testing.md

## 6.1 Project export and import

### 6.1.2 Project export, progress and media
- **Goal:** let an authenticated user download a portable archive for exactly one owned project.
- **Deliverables:**
  - Export the project, ordered and hidden `includes`, effective user overrides, attached notes,
    referenced user-owned dictionary-like records and their owned edges, and the shared dictionary
    subset required to resolve the project.
  - Include progress for the project's selected senses: memory and relevant review history.
    Include only media referenced by the exported project/content and accessible to the owner.
  - Produce a complete archive using the 6.1.1 serializers. Bound the work and avoid holding the
    full expanded archive in memory. An export must not include unrelated projects, another
    user's private rows/edges/media, or database credentials.
- **Acceptance:**
  - Real-database tests verify the archive's project tree, order/hidden state, overlays, notes,
    progress and media references against the source project.
  - Isolation tests seed another user's projects, edges and media and prove none are present in
    the archive. Tests also cover empty projects, shared-only data, missing/unreadable media and
    export failure cleanup.
  - The produced archive passes the current schema and reference validator and can be safely
    opened without exposing storage paths.
- **Docs:** import-export.md, overview.md, testing.md

### 6.1.3 Project import and merge
- **Goal:** merge a validated project bundle into the authenticated user's data without taking
  ownership of foreign rows or replacing existing learning state.
- **Deliverables:**
  - Validate the complete archive before mutation. Merge shared dictionary items by deterministic
    ID; create missing shared items only from validated shared bundle data and never overwrite
    existing shared rows.
  - Create/remap user-owned records, relationships, memberships, notes and media for the importing
    user. Remap every dependent reference and reject any edge whose owner or endpoints are not
    authorized by the import.
  - Import progress through an explicit option. Default it on only for a verified same-user
    restore and off for other bundles; when off, imported cards start new. When a memory row
    already exists for the importing user and sense, preserve that existing memory.
  - Apply rows and files as a recoverable operation with clear conflict/error reporting. A failed
    import must not leave partial memberships, rows or media.
- **Acceptance:**
  - Tests cover shared-ID merging without overwrite, user-owned ID/reference remapping, hidden and
    ordered memberships, repeated imports, conflicting identities and both progress-option paths.
  - Existing memory is preserved; progress-disabled imports create new cards; enabled imports
    retain valid bundled progress and review history without duplicating completion receipts.
  - Malformed archives, path traversal, oversized entries, foreign-owned edges, invalid media and
    database/file failures leave no partial imported data. Cross-user isolation is proven for
    imported records, edges and media.
- **Docs:** import-export.md, data-model.md, testing.md

## 6.2 Full user backup and site backup

### 6.1.4 User full backup and restore
- **Goal:** allow a user to preserve and restore all of their PandaWords data through the same safe
  merge semantics as project import.
- **Deliverables:**
  - Export every owned project, owned dictionary-like record and edge, notes, media, memory,
    review logs and user preferences in `pandawords.user`, with only the shared dictionary subset
    required by those records.
  - Restore into the currently authenticated user; never recreate or replace the account, role,
    password, tokens or global application configuration. Reuse the project import validators and
    remapping rules, with progress enabled by default for this full restore.
  - Make export/restore bounded and recoverable; preserve already-existing user records and memory
    according to the shared merge contract, and report conflicts rather than silently overwrite.
- **Acceptance:**
  - A full fixture backup/restore round-trip preserves all projects, associations, preferences,
    review history and media for the target user.
  - A restore into a different user remaps ownership and references; the source user's rows,
    preferences, media and credentials remain inaccessible and unchanged.
  - Repeated restore and interrupted export/import tests prove retry safety, no duplicate
    relationships or receipts, and cleanup of staged files/rows. Oversized or invalid backups
    fail explicitly before mutation.
- **Docs:** import-export.md, auth.md, data-model.md, testing.md

### 6.1.5 Admin site backup, restore and scheduled service
- **Goal:** provide a recoverable operator backup of the complete SurrealDB database and media
  volume, both on demand and on a schedule.
- **Deliverables:**
  - Implement the documented `pandawords.site` archive with `manifest.json`, a SurrealDB export
    and the full media volume. Record integrity/version metadata and preserve the lexicon
    exclusion; do not package `.env` files, keys or other server secrets.
  - Add the admin-authorized on-demand backup operation and a dedicated scheduled `backup`
    Compose service. Run backups daily, retain the configured number of recent complete backups,
    and avoid deleting a valid prior backup when a new backup fails.
  - Keep the existing pre-migration production backup behavior. Publish only complete,
    integrity-checked archives into a permission-restricted backup location.
  - Implement `deploy/restore.sh <archive>` as an explicit operator command. Preflight the
    archive, stop API/worker writes, restore the database into an empty database and restore
    media, verify the result, then restart services safely. On failure, return a nonzero result
    with an actionable stage and do not claim a successful restore.
- **Acceptance:**
  - Tests with disposable database/media resources cover on-demand and scheduled backups,
    archive integrity, retention, concurrent/failing backup behavior and permissions.
  - A restore round-trip reproduces database and media content in a fresh isolated environment;
    invalid archives, unsafe paths and database/media failures are detected without touching
    unrelated resources.
  - Authorization tests prove only administrators can request/download on-demand site backups.
    The web/API exposes no arbitrary site-restore upload; restore is an operator-controlled
    script. The lexicon and secrets are absent from the archive.
- **Docs:** import-export.md, deployment.md, testing.md

## 6.3 User interface

### 6.1.6 Export, import and backup UI
- **Goal:** expose project/user data portability to learners and on-demand site backup to
  administrators without weakening the backend authorization boundary.
- **Deliverables:**
  - Add localized project export/import controls and a user full-backup/restore entry point. Show
    archive validation, progress-import choice, bounded progress/status, success summary and
    retryable failures.
  - Add an administrator-only on-demand site-backup action and protected download. Do not expose
    site restore in the browser; operators use `deploy/restore.sh`.
  - Use the generated API client, existing form/dialog/feedback components and design tokens.
    Explain destructive/conflicting restore behavior before submission and preserve drafts/state
    when an operation fails.
- **Acceptance:**
  - Frontend tests cover project and user export, valid/invalid imports, progress choice, status,
    retries, cancellation where supported, and localized empty/loading/success/error states.
  - Authorization/navigation tests prove non-admin users cannot see or invoke site-backup
    controls, and user UI cannot target another user's data.
  - Browser tests complete a project export/import round-trip with progress both enabled and
    disabled; no credentials, local paths or unprotected media URLs appear in the UI.
  - API contracts are generated from the integrated backend and the production frontend build
    passes.
- **Docs:** overview.md, patterns.md, components.md, testing.md
