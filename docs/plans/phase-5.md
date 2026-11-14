# Phase 5 - Dual coding & mnemonics: task details

The format for each task is Goal, Deliverables, Acceptance and Docs. Dependencies, waves and
status are in [PLAN.md](PLAN.md). Read [data-model.md](../architecture/data-model.md),
[lexicon-pipeline.md](../architecture/lexicon-pipeline.md),
[learning-engine.md](../architecture/learning-engine.md), [components.md](../ui/components.md),
[patterns.md](../ui/patterns.md) and [testing.md](../dev/testing.md) for existing contracts.

## Dependencies and parallel execution

- **5.1.1** depends on 2.5.1 and 2.6.5; **5.1.2** depends on 3.2.5 and 2.6.5. Those
  prerequisites are complete, so both can start independently of each other and of Phase 4.
- **5.1.3** depends on 5.1.1 and 3.3.2. Start it after 5.1.1 is merged, verified and marked
  complete; it does not wait for 5.1.2 or any Phase 4 task. Recheck all statuses at launch.
- Use one coordinator for both phases: only that coordinator edits [PLAN.md](PLAN.md) and
  [PROGRESS.md](PROGRESS.md) on `main`, assigns task worktrees, and serializes merges, checks
  and status updates. Do not run two independent coordinators that edit or merge into the shared
  `main` simultaneously.
- Independent dependencies do not mean disjoint files. Phase 4 phrase/tag work and 5.1.1/5.1.2
  touch lemma detail and locales; 4.4.4 and 5.1.3 touch exercise integration. Partition work
  into separate components where practical and preserve both changes when integrating.
  Allocate distinct migration versions centrally, merge migrations one at a time, and regenerate
  the schema snapshot and generated API types from the integrated tree. Do not overwrite another
  task's migration, locale entries, API contract or shared component changes.
- Keep each test's database and media directory isolated. The dev stack, test DB server, ports
  and ignored data directories may be shared; do not reset or stop another task's resources.

## Shared implementation rules

- Migration `0007_media.surql` already supports image metadata and sense targets, and
  `0006_project_overlays.surql` already supports `note.kind = mnemonic`. Reuse these contracts;
  never edit or redefine an applied migration. Add forward-only schema only where required.
- An image attached by a user is owned by that user even when its sense is shared. Check both
  media and target visibility on every read and write; never expose or mutate another user's
  images, notes, preferences, jobs or cached inputs. Use bound SurrealQL in `backend/app/db/`.
- Upload and manual mnemonic editing work without Pixabay or DeepSeek. External searches and
  suggestions happen only on explicit user action; provider failures, missing keys and exhausted
  budgets are visible and never block ordinary study or erase a draft.
- All media used after selection is stored locally and delivered through the authenticated media
  endpoint. Do not expose storage paths, provider keys or bearer tokens; use opaque IDs, generated
  API types, localized English and Chinese text, existing components and design tokens.
- Use isolated fixtures and mocked providers for automated tests; no live Pixabay or DeepSeek
  calls are required. Every new user-data endpoint needs cross-user isolation coverage.

## 5.1 Images and mnemonics

### 5.1.1 Image upload and Pixabay attachment
- **Goal:** let a learner attach and manage private images for a visible sense, including an
  optional search of Pixabay.
- **Deliverables:**
  - Add authenticated, owner-scoped upload, list and removal operations for sense images. Verify
    the sense is visible to the caller, retain existing images and shared dictionary data, and
    return safe metadata and opaque media IDs. Reuse `media.store` and authenticated delivery;
    new uploads and Pixabay selections have `owner = current user`, not `NONE`.
  - Accept the existing JPEG, PNG, WebP and GIF media types only after checking the actual image,
    not just its filename or declared MIME. Limit encoded uploads and downloads to 10 MiB,
    individual frames to 25 million pixels, and animated images to 100 frames and 50 million
    pixels in total. Stream and bound incoming data; reject malformed, empty, unsupported,
    over-limit or mismatched content explicitly. Keep the reverse proxy's upload limit compatible
    with a valid 10 MiB file and bounded multipart overhead.
  - Add explicit, bounded Pixabay search and a user-selected download/attachment flow. Keep the
    key server-side, send only the chosen search query, show the Pixabay source on results and
    preserve available creator, source-page and license attribution on the saved image. Download
    the selected image through the backend before use; no permanent provider hotlinks.
  - Follow the [Pixabay API guidelines](https://pixabay.com/api/docs/): cache successful searches
    for 24 hours, honor rate limits and do not perform automated bulk searches/downloads. Keep
    search history and cached inputs owner-scoped. Search-result previews, if provided, use
    authenticated, bounded server-proxied responses rather than exposing arbitrary remote URLs.
  - Accept a server-validated search result identity, not a client-supplied download URL. Restrict
    outbound hosts and redirects to approved HTTPS provider endpoints, and enforce time, response
    and image limits. Use the existing worker/job pattern for downloads, with owner-bound payloads,
    explicit terminal errors and a safe retry. Recheck authorization before storing the result.
  - Make identical upload/download retries safe without duplicate attachments; reject conflicting
    reuse of a request identity. Clean up files on failed persistence and remove only the caller's
    attachment and unreferenced file. Never delete shared or other-user media.
  - Add a localized, accessible image section to each sense on the lemma detail page: upload,
    search/select, attribution, removal confirmation, loading, empty and retryable error states.
    Fetch protected images as authenticated blobs and revoke object URLs on replacement/unmount.
- **Acceptance:**
  - API and repository tests cover own/shared/foreign senses and images, unauthenticated access,
    invalid IDs, both upload and provider attachment, repeated/concurrent retries, deletion,
    missing files and rollback/cleanup. Another user cannot list, fetch, attach to or remove
    private targets or media.
  - Tests exercise every supported format, spoofed MIME, truncated/corrupt data, byte/pixel/frame
    boundaries, path traversal, unauthorized URLs/redirects, timeout and oversized downloads.
    Valid near-limit uploads also work through the deployed proxy configuration.
  - Mocked Pixabay tests cover 24-hour caching, owner isolation, attribution, rate limiting,
    disabled/missing key, empty results and failures; no provider URL is used for saved images.
    Frontend tests cover manual upload without a key, search/select, protected display, removal,
    failure/retry, locale, accessibility and object-URL cleanup.
- **Docs:** data-model.md, overview.md, lexicon-pipeline.md, patterns.md, deployment.md, testing.md

### 5.1.2 Mnemonic notes and optional suggestions
- **Goal:** let learners write their own mnemonics and optionally use a DeepSeek suggestion
  without automatically saving generated text.
- **Deliverables:**
  - Extend the existing note experience and `NoteEditor` to create, label, edit and delete
    `mnemonic` notes for the currently supported lemma, lexeme and sense targets. Reuse the
    existing owner-scoped note API and its validation; do not convert or overwrite ordinary notes.
    Preserve unsaved drafts across refresh, navigation and failed requests as the existing UI does.
  - Add an explicit suggestion action for the selected visible target. Use the existing worker/job
    and `services.llm.generate_json` contracts, daily budget, timeout, validated JSON and
    versioned cache. Job payloads contain only owner-bound IDs and a content version/key, not
    private note text; recheck visibility and content before dispatch and retrieval.
  - Send only the minimal target context needed for a suggestion. User notes, overrides and
    private context must never enter a shared cache or another user's response. Validate generated
    plain text and length before caching/display; render it as text, not executable markup.
  - Present the suggestion separately. Accepting it inserts it into an editable mnemonic draft;
    preserve existing unsaved text unless the user confirms replacing it. Only an explicit save
    creates or updates the user's note. Rejecting, cancelling, switching targets or a failed job
    must not create a note or replace an existing draft.
  - Show localized loading, unavailable, budget, provider and retry states. Manual mnemonic
    editing remains fully usable when generation is disabled or fails.
- **Acceptance:**
  - Note/UI tests cover creation, editing and deletion of both kinds, target changes, retained
    drafts, manual use with LLM disabled, and acceptance/edit/save versus reject/cancel.
  - Mocked LLM/job tests cover valid and invalid responses, cache scope, budget exhaustion,
    timeout, stale/deleted targets and late results after a target/user switch. Generation alone
    creates no note; an explicit save affects only the intended target and note kind.
  - API tests prove users cannot request or retrieve suggestions for another user's private
    target, notes, jobs or cache. No live provider call is needed.
- **Docs:** data-model.md, lexicon-pipeline.md, overview.md, patterns.md, testing.md

### 5.1.3 Image-to-word exercise and review media preferences
- **Goal:** use an attached image for optional recall while allowing each learner to control
  image and audio exercises in review.
- **Deliverables:**
  - Register `image2word` as a **recall** plugin in the production exercise registry. Select an
    available, authorized local image targeting the exact reviewed sense, with stable selection
    when several exist. Reuse selected-lexeme forms and the existing local answer normalization
    and grader; do not call Pixabay or an LLM while generating or grading an attempt.
  - Return only the protected media ID and a generic prompt before grading; keep answer forms
    private. Do not leak the answer through app-generated labels, filenames, alt text or source
    metadata. Display required attribution in a way that respects provider terms without
    revealing the answer; skip an image if both requirements cannot be met.
  - Missing, inaccessible, deleted, corrupt or wrong-target images make this plugin unavailable,
    not the whole review. Preserve existing selection rules: new/learning cards use recognition;
    review cards retain the existing recognition/recall weights and fallback behavior.
  - Add owner-scoped, persisted `prefs.review_images_enabled` and `prefs.review_audio_enabled`
    booleans, both defaulting to true; expose the existing US/UK `prefs.accent` alongside them.
    A forward-only migration backfills defaults without changing other preferences. Provide
    validated read/update operations that preserve theme, locale and desired retention.
  - Apply preference changes to **new** attempts only. Keep all plugins available for grading
    already-issued attempts, even if a preference changes mid-review. Disabling images or audio
    skips the corresponding media-dependent type; other eligible exercises remain available.
  - Render image prompts as authenticated blobs in the review page, rather than treating every
    `media_id` as audio. Add accessible localized controls and generic image alternative text,
    attribution and explicit loading/unavailable/retry states. Release object URLs and retain
    the existing give-up, exit, timing, grading and receipt-driven advancement behavior.
- **Acceptance:**
  - Plugin/API tests cover exact-sense and owner checks, multiple images, missing/corrupt media,
    selected forms, correct/wrong/give-up answers, no pre-grade answer leakage, and fallback
    without external services. Another user cannot obtain a private image through an attempt.
  - Preference tests cover defaults and migration of existing users, each toggle and accent,
    partial updates preserving other settings, persistence, invalid input and cross-user isolation.
    Changing a preference after issuance cannot invalidate grading or confirmation of that attempt.
  - Frontend and fixture-backed browser tests cover authenticated image display, both preference
    states, broken/deleted image recovery, keyboard/accessibility, object-URL cleanup, and a
    confirmed review plus retry with exactly one durable receipt. Exercise selection in tests is
    deterministic and does not add a production bypass. Existing audio and non-media reviews pass.
- **Docs:** learning-engine.md, data-model.md, overview.md, components.md, patterns.md, testing.md
