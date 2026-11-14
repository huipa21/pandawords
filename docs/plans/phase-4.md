# Phase 4 - Context & graph: task details

The format for each task is Goal, Deliverables, Acceptance and Docs. Dependencies, waves and
status are in [PLAN.md](PLAN.md); a task may start as soon as its own dependencies are complete.

Read [data-model.md](../architecture/data-model.md), [lexicon-pipeline.md](../architecture/lexicon-pipeline.md),
[learning-engine.md](../architecture/learning-engine.md), [components.md](../ui/components.md),
[patterns.md](../ui/patterns.md) and [testing.md](../dev/testing.md) for the existing contracts.
The dictionary records and edges used here already exist in migration `0005_dictionary.surql`.
In particular, `contains`, `used_in`, `part_of` and `member_of` are established schema; do not
redefine or edit migration `0005`. Task 4.2.1 verifies that contract and adds a forward-only
migration only if a concrete missing schema requirement is identified.

## Shared implementation rules

- Shared dictionary records and source-derived edges use `owner = NONE`; user-created sentences,
  passages, tags and relations, and edges that connect them, use the authenticated user's owner.
  Every record and edge read must independently filter for shared or requesting-user ownership.
  Endpoint existence or a visible endpoint does not authorize an edge.
- Keep lexicon/source ingestion deterministic and insert-only. Do not infer phrase components,
  literal phrase usage, sense links or morpheme decomposition from spelling alone. Use source
  structure or validated user choices; leave uncertain associations unlinked.
- `contains` always represents phrase composition, including idioms. A `used_in` link from a
  sense to a phrase represents literal usage only. Phrase meanings are ordinary phrase
  lemma/lexeme/sense records. Content references and spans must point to the original text.
- User text remains owner-scoped. Optional LLM work is never required for core behavior, follows
  the existing budget/cache/validation contract, and must not send private text or overlays to a
  shared cache or provider scope. Failed or unavailable generation leaves the user's content
  intact and reports an explicit state.
- Bound all graph, ingestion and list work. Oversized responses fail explicitly rather than
  silently truncating. Keep record IDs opaque in HTTP contracts, generate frontend API types,
  localize new UI text in English and Chinese, and use existing token/component/error patterns.
- Every new user-data endpoint needs cross-user isolation coverage. Use bound SurrealQL in
  `backend/app/db/`, forward-only migrations, and the isolated real-SurrealDB test harness.

## 4.1 Phrases

### 4.1.1 Phrase lexicon and `contains` materialization
- **Goal:** expose source-backed phrase components through the existing offline lexicon and
  shared dictionary graph.
- **Deliverables:**
  - Extend the lexicon build/reader contract to expose phrase lemmas and their ordered component
    lexemes, with stable IDs and source attribution. Preserve existing exact phrase lookup and
    multi-word lemma identity.
  - Materialize each phrase's `lemma(kind="phrase")`, phrase lexeme/senses and its `contains`
    edges idempotently. `contains.position` preserves component order; edge ownership follows the
    shared source record. A phrase's own senses remain separate from its component words.
  - Represent source-backed phrase components only when each component resolves to a valid
    English lexeme. Do not split arbitrary whitespace into guessed graph edges; report skipped or
    ambiguous mappings through the build's existing diagnostics.
  - Preserve the semantic distinction between phrase composition and literal word usage:
    `contains` is present for idioms, while a sense-to-phrase `used_in` edge is emitted only for
    an explicitly supported literal usage.
- **Acceptance:**
  - Offline build and fixture tests cover a multiword phrase, component ordering, stable identities,
    missing/ambiguous components, idiomatic phrase meaning, and a literal usage association.
  - Repeated materialization leaves existing shared rows and user-owned rows/edges unchanged and
    creates no duplicate `contains` edges. Cross-owner reads expose the shared graph but not
    private content or edges.
  - Phrase candidate lookup still distinguishes exact phrase matches from inflected word lookup.
- **Docs:** lexicon-pipeline.md, data-model.md, testing.md

### 4.1.2 Phrase add flow and phrases containing a word
- **Goal:** make phrases discoverable and addable without bypassing the existing project selection
  and ownership contracts.
- **Deliverables:**
  - Add an authenticated, bounded lookup for phrases containing a visible word/lexeme, backed by
    owner-safe `contains` traversal and stable ordering. Return phrase candidates and enough
    definition/source data to choose the phrase sense.
  - Extend the existing add-word flow to accept phrase candidates and selected phrase senses
    through the normal add-to-project/materialization path. Repeated adds are idempotent and do
    not replace other project selections or review state.
  - Show phrases containing the current word in the lemma detail experience, with a path to the
    phrase detail/add action. Render phrase/component identity accurately; do not imply literal
    sense usage merely because a word is a phrase component.
  - Add generated API contracts and localized empty, loading and error states.
- **Acceptance:**
  - API tests cover exact component matches, ordering, pagination/bounds, no matches, invalid
    targets, authentication and owner filtering for phrase records and edges.
  - Tests prove adding a phrase includes only the explicitly selected phrase senses and preserves
    existing memberships/card state on repeat or cross-project add.
  - Frontend tests cover phrase search/add, no-result/error states and navigation from a word to
    its phrase. API types are regenerated.
- **Docs:** overview.md, data-model.md, patterns.md, testing.md

## 4.2 Sentences, passages and reading

### 4.2.1 Sentence and passage schema contract
- **Goal:** verify the established sentence, passage, `used_in` and `part_of` schema against the
  ingestion and reading requirements without duplicating existing definitions.
- **Deliverables:**
  - Verify migration `0005_dictionary.surql` and `schema.snapshot.json` define SCHEMAFULL
    sentence/passage records with shared-or-owner fields, `used_in` from sense to lemma/sentence/
    passage with optional two-integer span, and ordered `part_of` from sentence to passage.
  - Add a new forward-only migration and update the snapshot only for a documented additive
    requirement that the existing schema cannot express. Never edit an applied migration or add
    a second definition of an existing table/edge.
  - Confirm the repository/API owner checks remain responsible for matching record and edge
    owners; endpoint enforcement alone is not authorization.
- **Acceptance:**
  - Fresh database, migration replay and snapshot-drift tests exercise the current contract and
    its typed fields/endpoints against SurrealDB 3.3.
  - If the existing schema is sufficient, no new migration is created; tests and documentation
    record that result. If it is not sufficient, regression tests prove the additive migration
    preserves prior data and schema.
- **Docs:** data-model.md, surrealdb-notes.md, testing.md

### 4.2.2 Sentence/passage CRUD and ingestion
- **Goal:** let a user save source text and link its occurrences to dictionary senses without
  exposing private content or guessing ambiguous meanings.
- **Deliverables:**
  - Add owner-scoped CRUD for sentences and passages, with strict text/language/translation
    validation and opaque IDs. A passage owns an ordered set of its sentences through `part_of`;
    standalone sentences remain supported.
  - Add an ingestion operation that stores a passage, splits it into sentences, preserves the
    original text and order, and creates `part_of` edges atomically. Retrying an ingestion request
    must not duplicate content or edges.
  - Tokenize and lemmatize sentence text using the existing offline lexicon services. Return
    candidate lemma/sense matches with spans against the original text; link only a resolved,
    user-confirmed or otherwise unambiguous sense through owner-bound `used_in` edges. Preserve
    unresolved occurrences for later selection instead of silently choosing a sense.
  - Permit optional LLM assistance for ambiguous sense suggestions only through the existing
    validated DeepSeek service. It must not be required for ingestion, and private text is
    owner-scoped input, never shared cache material.
  - Expose bounded owner-scoped reads for a passage and its sentences/occurrences, and CRUD for
    the user's own rows/edges. Deleting a passage handles its own relationships transactionally
    without deleting reused sentences or dictionary records.
- **Acceptance:**
  - Unit/integration tests cover sentence splitting, punctuation and Unicode spans, repeated
    occurrences, inflected forms, ambiguous/no-match words, manual resolution, ingestion retries,
    rollback, optional LLM unavailable/invalid results and sentence reuse.
  - API tests cover CRUD, malformed spans, ordering, bounds, authentication and cross-user access
    to records and associations. Foreign-owned rows/edges are neither returned nor modified.
  - Tests prove deleting one passage does not delete a sentence still used elsewhere and failed
    ingestion leaves no partial passage, sentence or edge set.
- **Docs:** data-model.md, overview.md, lexicon-pipeline.md, testing.md

### 4.2.3 Reading view
- **Goal:** provide a readable passage experience that connects text to the learner's effective
  project vocabulary and lets them add unknown words in context.
- **Deliverables:**
  - Add a responsive reading view for an owner's passage with sentence order and source text
    preserved. Highlight only words linked to senses visible in the selected project, and present
    the effective definition/gloss on selection.
  - Offer inline word lookup for unmatched text, allow the learner to choose a candidate/sense,
    then use the existing add-to-project and occurrence-link flow. Keep selection explicit where
    lemmatization or sense choice is ambiguous.
  - Distinguish unlinked, linked-to-project, and linked-but-not-selected/visible occurrences
    without leaking another user's project or sentence content. Preserve the passage if the
    learner dismisses or an add fails.
  - Localize controls and feedback; include loading, empty, retryable error and mobile states.
- **Acceptance:**
  - Frontend/API tests cover passage order, highlights for visible selected senses, hidden or
    absent memberships, multiple candidate senses, inline add success/retry, and unavailable
    passage states.
  - A cross-user test proves another user's passage and occurrence links are not readable through
    the reading API or embedded in project context. API types are regenerated.
- **Docs:** overview.md, patterns.md, components.md, testing.md

## 4.3 Tags and morphemes

### 4.3.1 Hierarchical tags and assignment
- **Goal:** let users organize visible dictionary content with reusable, owner-scoped tags.
- **Deliverables:**
  - Add owner-scoped tag create/read/update/delete and assignment APIs using the existing `tag`
    and `member_of` schema. Support user tags and tag-to-tag parent membership; keep shared
    source tags read-only.
  - Validate tag kind/name and target tables against the established model. Assignments may
    connect senses, morphemes and tags to a tag; each edge is owned by the user creating it and
    may target only shared or same-owner content.
  - Reject hierarchy cycles, foreign-owned targets, attempts to edit/delete shared tags and
    attempts to take over deterministic shared IDs. Deleting an owned tag removes only its own
    incoming/outgoing `member_of` edges and record atomically.
  - Add a localized assignment UI on the relevant word/morpheme surfaces, with loading/error
    states and reversible removal where appropriate.
- **Acceptance:**
  - Real-database tests cover shared and user tags, hierarchy and cycle rejection, duplicate
    assignment retries, deletion cleanup, visibility and cross-user isolation for rows and edges.
  - API tests reject owner/ID injection, unknown fields, unsupported targets and shared-tag writes.
    Frontend tests cover create/assign/remove and recoverable errors. API types are regenerated.
- **Docs:** data-model.md, overview.md, patterns.md, testing.md

### 4.3.2 Morpheme materialization and morph groups
- **Goal:** expose supported word-part structure from source etymology data and use it to relate
  genuinely shared morphology.
- **Deliverables:**
  - Extend enrichment/materialization to map supported lexicon etymology templates to existing
    shared `morpheme` records and ordered `composed_of` edges. Preserve source attribution and
    skip malformed, conflicting or unsupported analyses rather than deriving parts from spelling.
  - Map only validated morpheme identities to `morph_group` tags and `member_of` edges, so senses
    and morphemes that share an evidenced morpheme can participate in morphology-aware discovery
    and distractor selection.
  - An optional LLM fallback may propose decomposition only when source templates are absent;
    validate component types/order/identity before any write, record provenance, and leave the
    word unanalysed on unavailable, rejected or ambiguous output.
  - Add owner-safe reads for a lexeme's morphemes and related group members. User-created
    morphology remains private and cannot mutate or replace shared source data.
- **Acceptance:**
  - Fixture/build and repository tests cover supported root/affix templates, order, stable IDs,
    repeated components, malformed/conflicting templates, missing mappings, idempotent writes and
    provenance. No edge is inferred solely from prefix/suffix spelling.
  - Tests prove shared and user-owned morphology are filtered correctly, LLM failure creates no
    guessed rows, and morph-group candidates are deterministic and relation/owner-safe.
- **Docs:** lexicon-pipeline.md, data-model.md, learning-engine.md, testing.md

## 4.4 Graph exploration and context-aware exercises

### 4.4.1 Bounded graph API
- **Goal:** return an owner-safe, bounded subgraph around a focus record for graph exploration.
- **Deliverables:**
  - Add an authenticated API accepting a visible focus ID, bounded depth, and optional node-type
    and relation-type filters; return typed nodes and edges with effective fields and opaque IDs.
  - Define visible graph content as the union of the user's non-hidden project selections and
    their own dictionary records. Include an edge only when its owner is shared/requester and both
    endpoints are in the authorized visible set. Never expand through another user's edge or
    expose unselected dictionary records merely because they are nearby.
  - Apply deterministic ordering and a hard node cap (300, matching the graph UI contract).
    Report an explicit too-large response with guidance to reduce depth or filters; do not return
    an arbitrary partial graph. Validate that the focus is visible and supports the requested
    filters.
  - Include supported node/edge metadata needed by the legend and graph rendering, without
    leaking internal ownership fields or raw database IDs.
- **Acceptance:**
  - Integration/API tests cover depth, focus, each filter, edge direction, hidden project
    ancestors, shared/private nodes, user-created edges, empty graphs, stable order, cap/error
    behavior, malformed IDs and cross-user isolation.
  - Query count and result size remain bounded for dense fixtures; tests exercise the real
    SurrealDB query path rather than only mocked graph traversal.
- **Docs:** data-model.md, overview.md, testing.md

### 4.4.2 GraphCanvas and all-words view
- **Goal:** let learners explore their visible vocabulary as a graph without losing the familiar
  tree view.
- **Deliverables:**
  - Implement the documented `GraphCanvas`, `GraphLegend` and `GraphToolbar` catalogue entries
  using Cytoscape and graph/node/edge design tokens. Support focus selection, expand-on-demand,
    layout, depth and node/relation filters; never load/render the full graph by default.
  - Add the all-words page using the bounded graph API and the user's non-hidden project
    vocabulary plus their own dictionary content. Add the documented tree/graph toggle to the
    applicable vocabulary view; preserve project tree behavior and allow return to the same
    focus/selection where practical.
  - Map generated API responses into checked presentation models. Handle selection/navigation,
    empty/loading/error/too-large states and keyboard/touch interaction. Graph colors and shapes
    come only from the design tokens; localize all labels in both locales.
  - Add the components to `/dev/design` with representative dense, sparse, dark/light and
    responsive states.
- **Acceptance:**
  - Component tests cover node selection, expand events, filter/layout controls, theme token
    updates and accessible labels. Page tests cover tree/graph switching, focus/search, expansion,
    bounds/errors and empty data.
  - Visual review at mobile and desktop sizes confirms labels/legend remain usable and controls
    meet existing touch-target and token rules. Generated API types, lint and type checks pass.
- **Docs:** components.md, patterns.md, tokens.md, overview.md

### 4.4.3 User relation editing
- **Goal:** let users add and remove personal semantic links between visible senses without
  changing source relations.
- **Deliverables:**
  - Add owner-scoped create/list/delete operations for user `relates_to` edges, with validated
    relation type, visible sense endpoints and optional source metadata fixed to the user-created
    provenance.
  - Create edges with the authenticated owner; allow shared or same-owner endpoints only. Reject
    another user's custom sense, self-links where disallowed by the relation type, unsupported
    types and attempts to edit/delete a shared or foreign edge.
  - Make retries idempotent and duplicate conflicts explicit. The graph/detail UI exposes create
    and remove actions for supported relations and refreshes the bounded graph after success.
- **Acceptance:**
  - API/integration tests cover each permitted relation type, endpoint visibility/ownership,
    duplicate/retry behavior, invalid/self edges, shared-edge immutability and cross-user access.
  - Concurrent creation cannot take over or delete another user's edge. UI tests cover validation,
    success, retryable failure and removal. API types are regenerated.
- **Docs:** data-model.md, overview.md, patterns.md, testing.md

### 4.4.4 Context-aware exercises
- **Goal:** use the learner's own sentence context and validated tag/morphology graph to improve
  cloze prompts and distractors without weakening privacy or deterministic fallback behavior.
- **Deliverables:**
  - Extend cloze candidate selection to include owner-visible user sentences linked to the
    reviewed sense, in addition to existing safe source examples. Use a user sentence only for
    that same owner and never place it in a shared cache or another learner's attempt.
  - Extend distractor ranking to use available owner-safe concept/domain tags and morph groups,
    retaining existing synonym exclusion, deterministic ordering, bounded candidate counts and
    unavailable fallback when safe choices are insufficient.
  - Keep grading server-side and reuse the established attempt state, answer normalization and
    timing contracts. No LLM is required to produce or grade these exercises.
  - Regenerate API types only if the public exercise response contract changes; do not expose
    private source sentence metadata beyond what the learner needs to answer.
- **Acceptance:**
  - Tests cover source-versus-user sentence selection, span masking, repeated/inflected forms,
    hidden/deleted links, sentence owner isolation and fallback when no safe context exists.
  - Distractor tests cover owner-safe tag/morph tiers, synonym exclusion, insufficient candidates
    and deterministic fallback. API tests prove another user cannot obtain a private sentence
    through an attempt, prompt, cache or response.
  - Exercise review continues to create one correct owner-scoped review result and does not change
  SRS behavior for prompts lacking Phase 4 context.
- **Docs:** learning-engine.md, data-model.md, testing.md
