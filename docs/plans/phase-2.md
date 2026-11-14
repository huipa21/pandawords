# Phase 2 — Dictionary & projects: task details

The format for each task is Goal · Deliverables · Acceptance · Docs. Dependencies and waves are
in [PLAN.md](PLAN.md). A task may start as soon as its own dependencies are ✅; Phase 1 does not
need to be complete as a whole.

## 2.1 Lexicon pipeline

### 2.1.1 Lexicon download scripts
- **Goal:** fetch the upstream datasets reproducibly, without coupling downloads to the build.
- **Deliverables:**
  - Scripts under `backend/scripts/` to download kaikki English JSONL, ECDICT CSV and OEWN data.
  - Store source files under `data/lexicon/raw/`; use official sources first and the configured
    fallback source only after an official source fails.
  - `manifest.json` recording source, version or retrieval date, license and checksums for each
    downloaded artifact.
  - Document the observed source fields and download/build commands in `backend/scripts/README.md`.
- **Acceptance:**
  - Each source can be fetched independently and is verified against the manifest.
  - Re-running a download does not silently replace a file with content that disagrees with its
    recorded checksum.
  - A failed download reports which source failed and does not leave a valid-looking partial file.
- **Docs:** lexicon-pipeline.md, backend/scripts/README.md

### 2.1.2 Build the core SQLite lexicon
- **Goal:** turn kaikki into the canonical offline dictionary backbone.
- **Deliverables:**
  - A streaming build command producing `data/lexicon/lexicon.sqlite`.
  - Core `lemma`, `lexeme`, `sense`, `pron`, `form` and `form_index` tables with stable keys and
    the fields defined in [data-model.md](../architecture/data-model.md) and
    [lexicon-pipeline.md](../architecture/lexicon-pipeline.md).
  - Preserve source attribution and US/UK pronunciation and audio metadata when available.
  - Add the required lookup indexes and make the output safe to replace only after a successful
    build.
- **Acceptance:**
  - A build from the downloaded source completes without loading the complete JSONL into memory.
  - Tests cover malformed or incomplete source records, stable IDs, multiple lexemes and senses,
    and form-to-lemma lookup.
  - The resulting SQLite database passes integrity checks and its schema matches the documented
    tables.
- **Docs:** lexicon-pipeline.md, backend/scripts/README.md

### 2.1.3 Merge ECDICT and wordfreq
- **Goal:** enrich the core lexicon with Chinese glosses, exam metadata and frequency.
- **Deliverables:**
  - Extend the build to import ECDICT Chinese glosses and exam tags, and wordfreq Zipf values.
  - Apply the documented `common` selection rules using frequency and primary ECDICT glosses.
  - Record source attribution and handle unmatched or ambiguous source entries explicitly.
- **Acceptance:**
  - Tests cover successful matching, unmatched entries, duplicate glosses, exam tags and frequency
    values, and the `common` selection rules.
  - Rebuilding with the same inputs produces the same logical data and does not duplicate rows.
- **Docs:** lexicon-pipeline.md, backend/scripts/README.md

### 2.1.4 Align OEWN relations
- **Goal:** attach WordNet relations to the closest available lexicon senses.
- **Deliverables:**
  - Import OEWN synonym, antonym, hypernym and hyponym relations and lexnames.
  - Align relations by gloss overlap as described in lexicon-pipeline.md; record approximate
    fallback alignments with `source='oewn:approx'`.
- **Acceptance:**
  - Tests cover exact and approximate alignments, below-threshold matches, absent glosses and
    relation direction/type.
  - No relation is emitted with a missing endpoint or an invalid type.
- **Docs:** lexicon-pipeline.md, backend/scripts/README.md

### 2.1.5 Fixture lexicon and `LexiconReader`
- **Goal:** provide a small deterministic lexicon for tests and a typed runtime read interface.
- **Deliverables:**
  - `backend/tests/fixtures/lexicon_small.sqlite`, built by the production build pipeline from a
    curated word list.
  - The fixture covers roughly 50 words, including polysemy, phrases, US/UK pronunciations and
    derivations.
  - `LexiconReader` for read-only access to lemma, form, lexeme, sense, relation, gloss, tag and
    frequency data needed by the APIs and jobs.
  - Keep database connection and query behavior behind the service rather than exposing SQLite
    details to callers.
- **Acceptance:**
  - Fixture generation is repeatable and uses the same transformations as the full build.
  - Unit tests verify representative exact lemma, inflected-form, phrase, sense and relation reads.
  - The reader opens the fixture read-only and returns a clear error for a missing or invalid
    lexicon database.
- **Docs:** lexicon-pipeline.md, testing.md

### 2.1.6 `dev.ps1 lexicon` and release artifact
- **Goal:** make the lexicon build and transfer artifact a repeatable developer command.
- **Deliverables:**
  - `dev.ps1 lexicon` to download missing sources, build the database and create a dated
    `pandawords-lexicon-<date>.tar.gz` artifact.
  - Include the manifest and checksums in the artifact; keep raw source data and generated files
    under ignored `data/`.
  - Use the release/build conventions established by task 1.6.5 without adding the lexicon to
    site backups.
- **Acceptance:**
  - The command works from the main worktree and another linked worktree, using the shared
    lexicon data location.
  - The artifact can be unpacked and its database passes SQLite integrity checks.
  - Download, build and packaging failures return a non-zero exit code and identify the failed
    stage.
- **Docs:** setup.md, deployment.md, lexicon-pipeline.md

## 2.2 Shared dictionary

### 2.2.1 Dictionary tables and edges
- **Goal:** add the shared dictionary schema used when words are materialized from SQLite.
- **Deliverables:**
  - Forward-only migration(s) defining the dictionary tables and relation edges in
    [data-model.md](../architecture/data-model.md), including ownership, fields and minimum
    indexes.
  - Update the generated schema snapshot.
- **Acceptance:**
  - Migration integration tests apply the schema to a fresh database and a repeat run is safe.
  - Tests verify the documented field types, indexes, relation endpoints and `owner` fields.
  - Schema drift checks pass against the regenerated snapshot.
- **Docs:** data-model.md, surrealdb-notes.md

### 2.2.2 Deterministic keys and `rid` helpers
- **Goal:** centralize shared dictionary identity and safe API record-ID conversion.
- **Deliverables:**
  - Deterministic key helpers for lemma, lexeme and sense IDs, following the rules in
    data-model.md.
  - `rid` encode/decode helpers for URL-safe API IDs, validating the expected table and preserving
    structured SurrealDB record IDs.
- **Acceptance:**
  - Unit tests show stable keys for normalized inputs and distinct keys for distinct POS,
    etymology and sense identity.
  - `rid` round-trips supported IDs and rejects malformed values or IDs for an unexpected table.
- **Docs:** data-model.md, conventions.md

### 2.2.3 Dictionary repository
- **Goal:** materialize shared lexicon data once and expose owner-safe effective reads.
- **Deliverables:**
  - A repository that materializes a lemma, its lexemes, selected senses and supported dictionary
    edges from `LexiconReader` using deterministic IDs and idempotent writes.
  - Effective reads that combine shared (`owner = NONE`) and requesting-user rows, apply the
    user's overrides, and never expose another user's rows or edges.
  - Focused query helpers for data needed by project and discovery APIs.
- **Acceptance:**
  - Integration tests prove repeated materialization does not create duplicates and leaves
    existing user-owned overrides/content intact.
  - Cross-user isolation tests prove user-owned rows and edges are invisible to another user while
    shared rows remain readable.
  - Tests verify effective reads apply overrides without mutating shared records.
- **Docs:** data-model.md, testing.md

## 2.3 Projects and user dictionary data

### 2.3.1 Project and overlay migrations
- **Goal:** add projects and the per-user dictionary overlay schema.
- **Deliverables:**
  - Forward-only migration(s) for `project`, `includes`, `override` and `note`, with fields and
    indexes from data-model.md.
  - Update the schema snapshot.
- **Acceptance:**
  - Migration tests apply to a fresh database and verify the project-to-item relationship,
    reversible `hidden` membership, override identity and note ownership.
  - Schema drift checks pass.
- **Docs:** data-model.md, surrealdb-notes.md

### 2.3.2 Project CRUD API
- **Goal:** let an authenticated user create and manage their projects.
- **Deliverables:**
  - User-scoped project create, list, read, update and delete endpoints, with request/response
    models and pagination consistent with API conventions.
  - Project ownership checks on every operation.
- **Acceptance:**
  - API tests cover CRUD behavior, validation, pagination and not-found behavior.
  - Cross-user isolation tests prove a user cannot read, change or delete another user's project.
- **Docs:** overview.md, data-model.md, testing.md

### 2.3.3 Overrides, custom senses and notes API
- **Goal:** support user edits and annotations without changing shared dictionary data.
- **Deliverables:**
  - APIs to create, read, update and remove a user's field overrides on visible dictionary items.
  - APIs to create user-owned custom senses and manage notes on permitted targets.
  - Validate target ownership/visibility and apply owner filters to every read and write.
- **Acceptance:**
  - API tests cover override application/reset, custom sense ownership and note CRUD.
  - Cross-user isolation tests prove another user cannot read or modify the custom senses,
    overrides or notes.
  - Tests verify a shared dictionary row is unchanged after an override or custom-sense operation.
- **Docs:** data-model.md, testing.md

### 2.3.4 Project tree query and API
- **Goal:** return the effective, visible dictionary tree for one project.
- **Deliverables:**
  - An owner-scoped query and API for project lemmas, lexemes and selected senses.
  - Respect `includes` membership and `hidden` state at each tree level, and apply effective
    overrides.
  - An API to hide and unhide project items by updating their `includes` edges; hiding must not
    delete dictionary rows or membership history.
  - Return stable identifiers and the content needed by `LemmaTree` and lemma detail views.
- **Acceptance:**
  - Integration/API tests cover empty projects, selected senses, hidden items, hidden ancestors,
    overrides, hide/unhide and pagination or bounded-result behavior.
  - Cross-user isolation tests prove project contents and user-owned rows cannot cross owners.
- **Docs:** data-model.md, testing.md

## 2.4 Discover and add words

### 2.4.1 Lemmatization and candidates API
- **Goal:** resolve entered words and phrases to useful dictionary candidates.
- **Deliverables:**
  - Normalize input, look up exact lemma and phrase matches, and use spaCy plus `form_index` for
    inflected word forms.
  - Authenticated candidates API returning lexemes and senses, including `common` defaults and
    source metadata needed for selection.
  - Run CPU-heavy lemmatization outside the request event loop.
- **Acceptance:**
  - Tests cover exact lemma, inflected form, phrase, unknown input, multiple candidates and
    malformed/empty input.
  - API tests verify authentication and that candidate data comes from the configured lexicon.
- **Docs:** lexicon-pipeline.md, testing.md

### 2.4.2 Add to project
- **Goal:** materialize selected dictionary data and include it in a user's project.
- **Deliverables:**
  - Authenticated endpoint to add a candidate lemma and selected senses to a project.
  - Materialize shared rows through the dictionary repository; create project `includes` edges and
    enqueue the required enrichment and audio jobs.
  - Make repeated requests safe and preserve the user's selected senses and existing overrides.
- **Acceptance:**
  - Integration tests cover a new add, repeated add, selecting a subset of senses, an invalid
    project and job enqueueing.
  - Cross-user isolation tests prove one user cannot add content to another user's project.
- **Docs:** lexicon-pipeline.md, data-model.md, testing.md

### 2.4.3 Enrichment job
- **Goal:** enrich newly materialized dictionary items with available graph relations and metadata.
- **Deliverables:**
  - An `enrich` worker handler that materializes applicable relations to already materialized
    items and attaches frequency and exam-tag data from the lexicon.
  - Idempotent processing that does not overwrite per-user edits or create duplicate edges.
- **Acceptance:**
  - Worker tests cover successful enrichment, retryable failures, repeated execution and missing
    optional source data.
  - Integration tests verify relation type, provenance, edge ownership and frequency/tag results.
- **Docs:** lexicon-pipeline.md, testing.md

## 2.5 Audio and media

### 2.5.1 Media storage and authenticated serving
- **Goal:** store audio assets and serve them only through an authorized application path.
- **Deliverables:**
  - Media storage using the configured media directory, metadata persistence and safe relative
    paths.
  - Authenticated media endpoint that authorizes the target and uses `X-Accel-Redirect` for file
    delivery through the internal nginx location from task 1.6.3.
  - Validate media kind and content type and avoid exposing filesystem paths.
- **Acceptance:**
  - API tests cover authorized access, unauthenticated access, inaccessible targets and missing
    files.
  - Path and metadata validation tests reject traversal or invalid media paths.
- **Docs:** overview.md, data-model.md, deployment.md, testing.md

### 2.5.2 Audio job
- **Goal:** provide US and UK pronunciation audio when source recordings are available.
- **Deliverables:**
  - An `audio` worker handler that tries the Wiktionary recording first and falls back to
    edge-tts for the configured US/UK voices.
  - Store generated/downloaded audio through the media service, with source and attribution
    metadata; reuse cached shared audio.
  - Apply the documented Wikimedia User-Agent and request throttling rules.
- **Acceptance:**
  - Tests with mocked downloads and TTS cover source success, fallback, missing voices, retries,
    cache reuse and metadata.
  - A failure to obtain optional audio does not fail the add-word operation.
- **Docs:** lexicon-pipeline.md, setup.md, testing.md

## 2.6 Project and word UI

### 2.6.1 Word components and previews
- **Goal:** implement reusable dictionary display and selection components.
- **Deliverables:**
  - Components in `src/components/word/` from components.md: `WordHeader`,
    `PronunciationChip`, `AudioButton`, `PosBadge`, `NodeTypeBadge`, `RelationBadge`,
    `ExamTagBadge`, `SenseItem`, `SenseSelectList`, `LexemeBlock`, `LemmaTree` and `NoteEditor`.
  - Add shared components to `/dev/design` with representative word, phrase, pronunciation,
    sense-selection and tree states.
  - Follow the design tokens, responsive patterns and bilingual i18n conventions.
- **Acceptance:**
  - Component tests cover sense selection defaults, hidden/override states and audio controls.
  - Preview route displays the shared components in light/dark themes and at mobile/desktop widths.
  - UI text has both `zh-CN` and `en` translations.
- **Docs:** components.md, patterns.md

### 2.6.2 Projects pages
- **Goal:** let users create, view, edit and delete projects from the frontend.
- **Deliverables:**
  - Projects list and create/edit pages connected to the project API.
  - Responsive desktop and mobile layouts, form validation, destructive-action confirmation and
    loading, empty and error states.
  - Bilingual UI strings and API error-code mappings.
- **Acceptance:**
  - Tests cover form validation, list states and API error handling.
  - Pages work at 375px and 1280px and all CRUD actions work against the dev API.
- **Docs:** patterns.md

### 2.6.3 Add-word dialog
- **Goal:** provide the search, candidate selection and add flow from a project.
- **Deliverables:**
  - Responsive dialog/drawer for input, candidate results and `SenseSelectList` selection.
  - Submit to the add-to-project API and show asynchronous job progress with `JobStatus`.
  - Handle no matches, loading, recoverable errors and repeat adds.
- **Acceptance:**
  - Tests cover candidate selection, common-sense defaults, submit state and API/job errors.
  - A user can add a word and see its background job status without blocking the page.
- **Docs:** patterns.md, components.md

### 2.6.4 Project tree view
- **Goal:** show and manage the dictionary items included in a project.
- **Deliverables:**
  - Project tree page using `LemmaTree` and the project tree API.
  - Hide/unhide actions for project items; hiding is reversible and offers Undo rather than deleting
    dictionary data.
  - Loading, empty, error and data states, with responsive behavior.
- **Acceptance:**
  - Tests cover tree rendering, hide/unhide, Undo and API errors.
  - Hidden items leave the visible tree and can be restored without re-adding the word.
- **Docs:** patterns.md, data-model.md

### 2.6.5 Lemma detail page
- **Goal:** inspect a lemma and manage its senses, overrides, notes and pronunciation.
- **Deliverables:**
  - Detail view using shared word components and effective dictionary data.
  - Support editing/resetting a user's override, adding/editing notes, and playing available
    pronunciation audio.
  - Preserve user edits when refreshing or navigating between project views.
- **Acceptance:**
  - Tests cover effective values, override reset, notes, missing audio and API errors.
  - Edits affect only the current user and update the displayed effective content.
- **Docs:** patterns.md, data-model.md

### 2.6.6 Project-to-word E2E
- **Goal:** verify the complete core dictionary workflow through the browser.
- **Deliverables:** one E2E test that creates or opens a project, adds a fixture word, edits a sense
  override and hides that sense.
- **Acceptance:**
  - The test uses the local fixture lexicon and does not depend on live dictionary downloads or
    external audio services.
  - It verifies the changed sense is visible to the user and that hiding it removes it from the
    project tree without deleting its underlying dictionary data.
- **Docs:** testing.md
