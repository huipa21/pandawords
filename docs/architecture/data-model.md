# Data model (SurrealDB 3.3)

## Personal semantic relations (4.4.3)

The existing `relates_to` schema supports synonym, antonym, hypernym, hyponym,
confusable, collocation and default (related). All personal links are directional;
all seven types require distinct sense endpoints. Shared senses must actually be
selected and visible in the learner's project union; requester-owned senses are also
eligible. General dictionary lookup alone does not grant relation-editing visibility.
Both endpoint owners and the edge owner are checked independently, including on list
and removal. Shared source edges remain read-only and foreign edges are not exposed.

Creation fixes `owner` to the authenticated user and `source` to `user`; neither
ownership, provenance nor IDs can be submitted. A deterministic primary identity
hashes owner, ordered endpoints and type. Insert-only transactions with conflict
retries give concurrent identical requests one edge; an existing matching personal
edge is returned explicitly with `created: false`. Protected identity collisions
return 409 and are never overwritten. No migration or source-row change is needed.

### Evidenced morphology (4.3.2)

Migration 0021 adds optional `source` to morpheme/composed_of/member_of and an
owner/in/order composition index; existing records remain unchanged. Shared source-backed
morpheme keys are `[en,text,type,etymology_no]`, group tag keys
`[morph_group,...morpheme_key]`. Composition identity includes provenance and zero-based
order, retaining repeated components. Membership connects only evidenced morphemes and
selected senses to these groups. Reads authorize edge, source endpoint and target endpoint
independently. User-owned morphology is visible only to its owner and never replaces
shared source composition. See the lexicon pipeline for validation and absence diagnostics. (SurrealDB 3.3)

## Hierarchical user tags (4.3.1)

Tag API kinds are `custom`, `concept`, `domain`, and `morph_group`; names are trimmed,
nonempty and at most 200 characters. Server-generated opaque tag IDs cannot replace source IDs.
`member_of` connects only sense/morpheme/tag to tag. Every user edge owns both its authorization
and its identity: reads check edge, source and destination visibility independently. Shared edges
are read-only; users may add/remove their own edges between visible endpoints, including shared tags.
Cycles are checked across the owner's and shared visible edges, including self-parenting.
Migration 0018 adds indexed owner/source/destination lookups and `user.tag_revision`; real revision
writes serialize each owner's hierarchy mutations and make duplicate assignment retries idempotent.
Owned tag deletion and own incoming/outgoing edge cleanup share a transaction. Because SurrealDB
automatically cascades all incident relation edges, a tag with foreign/shared incident edges
fails closed with `409 tag.in_use` instead of deleting protected edges. Such edges cannot be
created through another owner's tag API, but the guard also protects imported/corrupted graphs. (SurrealDB 3.3)

The source of truth for the current schema is `backend/app/db/schema.snapshot.json` (generated)
plus the migrations. This doc explains the intent. Syntax details: [../dev/surrealdb-notes.md](../dev/surrealdb-notes.md).

## Two layers

### Review media preferences (5.1.3)

Migration `0020_review_media_preferences.surql` adds `user.prefs.review_images_enabled` and
`review_audio_enabled` as booleans defaulting to true. A single conditional update backfills
both missing fields while retaining existing false values and every other preference.
The owner-bound review preference repository uses fixed per-field conditional assignments,
never replaces `prefs`, and exposes the existing accent alongside the media toggles.
Image attribution is stored in the attempt's existing private JSON payload/public prompt only
after the image plugin's anti-answer-leak checks; no new image/attempt table is needed.

### Private sense images (5.1.1)

`media` image rows always use the attaching user's owner, including shared sense targets.
The image list returns only that user's attachments; protected delivery additionally checks
current target visibility. Removal never changes a dictionary sense or another owner's row.
Migration `0019_images.surql` adds owner-bound `image_request` retry tombstones (target,
fingerprint, provider identity, optional media reference) and JSON-text `image_search` entries
with a 24-hour expiry. Request identities are hashed with the owner and conflicting reuse is
409; deleted attachments cannot be resurrected by a late retry. Atomic request/media writes
serialize concurrent retries, and aborted transactions remove their unique local files.
`image_rate` coordinates owner search/queue limits; `image_provider_rate` contains only global
provider counters, never queries, owners or search results.

### Graph exploration authorization (4.4.1)

Graph visibility is narrower than general dictionary lookup: the union of nonhidden
project selections belonging to the requester, plus every requester-owned dictionary record.
A hidden lemma or lexeme also hides selected descendants **in that project**. A visible
selection in another owned project still authorizes the record; own dictionary rows remain
independently authorized. Hidden ancestry follows only shared/requester-owned hierarchy edges
with independently authorized owners on both endpoints. It also works without an intermediate
lexeme membership marker. Nearby unselected shared dictionary records are never implicitly added.

Both edge endpoints must belong to this set, and the edge itself must be shared/requester-owned.
Node/relation filters are applied before expansion, so excluded nodes cannot act as bridges.
One transaction provides the authorization/traversal/effective-field snapshot. Batched reads
avoid per-node queries: depth at most 3, at most 300 returned nodes and 10,000 matching edges.
Authorization reads reject more than 10,000 project memberships, own rows per dictionary table,
or hierarchy edges per hierarchy relation. Each query uses a limit plus one sentinel;
overflows fail explicitly rather than truncate. These operational authorization bounds can
also produce `graph.too_large` before traversal. No migration is needed.

1. **Shared dictionary**: canonical linguistic data, materialized from the lexicon the first time
   any user adds a word. These rows have `owner = NONE` and are read-only for users.
2. **Per-user layer**: projects, project membership/hiding, overrides, user-created content, notes,
   media, memory and review logs. These rows have `owner = user:<id>`.

User-created dictionary-like rows (a custom sense, sentence, passage, tag or relation) live in the
same tables as shared rows, but with `owner` set. **Every read filters `owner = NONE OR owner = $user`.**
Edges carry `owner` too, so a user's custom sense attached to a shared lexeme stays invisible to others.

Migration `0005_dictionary.surql` introduces all seven dictionary tables and all nine dictionary
edges below as SCHEMAFULL, with `owner: option<record<user>>` on each. Omitted ownership is
shared (`NONE`); `NULL`, strings and references to other tables are rejected. This is a storage
contract, not database-level authorization: repositories must apply the owner filter on every
record and edge read.

## Exercise attempts (3.2.1)

Forward migration `0017_exercise_attempts.surql` adds SCHEMAFULL `exercise_attempt`:
`owner: record<user>`, `project: record<project>`, `sense: record<sense>`,
`status: 'open' | 'graded' | 'confirmed'`, `issued_at`, `expires_at` (strictly later than
issuance) and `payload: string`. Index `exercise_attempt_owner_expiry(owner, expires_at)`
supports owner-bound expiry maintenance; point operations use the random primary ID plus owner
filter. Version 0016 is independently allocated to daily planning.

The private payload is validated/serialized by `domain.exercises.Attempt`, including the
public prompt, private answer specification, issuance memory version, hint flag, immutable
submission fingerprint/grade, server elapsed, `GradedReview` and optional confirmed receipt.
JSON text preserves Pydantic's exact contract without SurrealDB dropping optional/nested fields.
All mutations use conflict-retried SDK transactions; simultaneous hint/answer writes serialize
on this record. No public dictionary or graph read traverses attempt payloads.

Every repository read/update filters `owner = $user`; services also validate the payload's owner
and identity. Foreign, missing and malformed IDs return indistinguishable `exercise.not_found`.
Attempts do not replace `review_log`'s unique owner/attempt completion identity: the existing SRS
transaction remains the authority for exactly-once scheduling and durable receipts. No cascade
removes confirmed attempts or review receipts on project deletion. Unconfirmed rows stop being
usable after 30 minutes; this task does not delete historical rows automatically.

## Record IDs

Shared rows use deterministic IDs, so materialization is idempotent and imports merge cleanly:

| Table | ID |
|---|---|
| `lemma` | `lemma:['en', 'run']`, `lemma:['en', 'kick the bucket']` (normalized lowercase text) |
| `lexeme` | `lexeme:['en', 'run', 'verb', 1]` (lemma, part of speech, etymology number) |
| `sense` | `sense:['en', 'run', 'verb', 1, '<key>']`. `key` = source sense id if stable, else the first 12 chars of sha1(normalized gloss) |
| `morpheme` | `morpheme:['en', 'pre-', 'prefix']` |
| `tag` (shared) | `tag:[<kind>, <slug>]` |

User-created rows generally use random IDs. Private sentence/passage ingestion uses SHA-256
identities over the authenticated owner and exact input fields: identical retries and identical
sentence text/language/source/translation reuse rows; changing a passage title produces a separate
passage sharing unchanged sentences. These IDs still use the opaque record-ID transport.

### Private reading content (4.2.2)

`/api/content` CRUD exposes only `owner = $user` sentences/passages, never shared rows.
`part_of` is sentence → passage with zero-based `order`; repeated identical sentence text
can reuse one sentence row at multiple positions through distinct deterministic edges.
Offsets are half-open **Unicode code-point** pairs, not UTF-8 bytes or JavaScript UTF-16 indices.
Passage parts include their original passage span; occurrences use sentence-relative spans.
Whitespace, combining characters, punctuation and original casing are never normalized in storage.

Ingestion inserts the passage, reused/new sentences, ordered associations, materialized unambiguous
dictionary senses and owner-bound `used_in` edges in one conflict-retried SDK transaction.
Unmatched/ambiguous occurrences are reconstructed from persisted source text and the offline lexicon;
only confirmed/unambiguous resolutions are persisted as edges. Lexicon upgrades may therefore change
unresolved candidates, but persisted confirmations remain authoritative.
Both edge ownership and endpoint visibility are checked; ENFORCED alone is not authorization.
An exact retry preserves manual resolutions. If a deterministic row was edited, retry returns 409
rather than overwriting it. Full replacement updates clear that row's own stale associations.
Passage deletion removes only its owned relationships and passage row, never sentence or dictionary
rows. Sentence deletion clears its owned associations but never deletes passages or senses.
Because SurrealDB automatically deletes all graph edges when deleting an endpoint, malformed
foreign-owned associations block deletion with 409 instead of silently cascading another
owner's edges. Full replacement updates use UPDATE, not DELETE/recreate, to preserve such edges.

Context-aware cloze (4.4.4) reads these same persisted `used_in.span` offsets against the
original sentence text, never offsets into a normalized copy. Both the relation and sentence
must belong to the authenticated learner; the sense must be shared or owned by that learner.
Project-hidden sentence memberships and deleted/stale associations are not exercise sources.
Only the masked sentence enters that owner's durable attempt, with no private sentence
metadata in the public prompt and no shared-cache writes. No new schema is required.
Concept/domain and morph-group distractor discovery independently authorizes memberships,
tags, candidate senses and their ancestry; it never infers morphology from spelling.

`app/domain/dictionary_keys.py` is the shared source of lemma, lexeme and sense keys:
`lemma_key(lang, text)`, `lexeme_key(lang, text, pos, etymology_no=1)` and
`sense_key(lang, text, pos, etymology_no=1, *, source_sense_id=None, gloss=None)`.
Each returns the array used in `RecordID(table, key)`; it does not access the database.
Language, lemma text, POS and fallback gloss are Unicode NFKC-normalized, case-folded, stripped
and have whitespace runs collapsed to one space. Blank components are rejected. POS names are
not aliased: callers must supply the canonical source POS. Etymology numbers are positive integers
(not booleans); distinct POS and etymology values remain distinct identities.

A nonblank stable source sense ID takes precedence over the gloss and is preserved verbatim
(case-sensitive and not normalized). Without one, the sense key is the first 12 lowercase hex
characters of SHA-1 over the normalized gloss's UTF-8 bytes. Missing or blank identity is an error.
Gloss edits change fallback identity, but not source-ID identity. The truncated hash is an
identity fallback, not a security primitive or a collision-free guarantee.

API transport uses `app/core/record_ids.py`; see [conventions](../dev/conventions.md#api).

## Dictionary tables

| Table | Fields |
|---|---|
| `lemma` | `text`, `lang`, `kind` (`word`\|`phrase`), `freq_zipf`, `cefr?`, `exam_tags[]` (ielts, toefl, cet4…), `source`, `owner` |
| `lexeme` | `pos`, `etymology_no`, `etymology_text?`, `forms[] {form, tags[]}`, `pron[] {accent: US\|UK, ipa, audio?: media}`, `owner` |
| `sense` | `definition`, `gloss {zh?: string}` (keyed by source language), `register[]`, `domain[]`, `examples[]` (short source examples), `rank` (order in source), `common` (bool), `source`, `owner` |
| `morpheme` | `text`, `type` (prefix\|root\|suffix\|infix), `meaning?`, `owner` |
| `tag` | `kind` (morph_group\|concept\|domain\|custom…), `name`, `owner` |
| `sentence` | `text`, `lang`, `translation {zh?}`, `source`, `owner` |
| `passage` | `title`, `text`, `lang`, `source`, `owner` |

## Dictionary edges (all `TYPE RELATION`, all with `owner`)

| Edge | From → To | Fields |
|---|---|---|
| `has_lexeme` | lemma → lexeme | |
| `has_sense` | lexeme → sense | `rank` |
| `composed_of` | lexeme → morpheme | `order` |
| `derives_to` | lexeme → lexeme | `via?` (affix/process) |
| `relates_to` | sense → sense | `type`: synonym\|antonym\|hypernym\|hyponym\|confusable\|collocation\|default; `source` |
| `member_of` | sense\|morpheme\|tag → tag | |
| `contains` | lemma(phrase) → lexeme | `position` |
| `used_in` | sense → lemma(phrase)\|sentence\|passage | `span? [start, end]` |
| `part_of` | sentence → passage | `order` |

Distractor discovery (3.2.2) reuses sense → tag `member_of` for `concept`/`domain` and
optional `morph_group` tags, sense → sense `relates_to` (`confusable` and `synonym`, both
directions), and visible `has_sense`/`has_lexeme` ancestry for POS and lemma `freq_zipf`.
It introduces no persisted fields or migration. The internal `domain.distractors` pool
contains only owner-visible effective display fields and ranking tiers, not raw graph rows.

Phrase rule: source-backed `contains` represents composition even for idioms. `sense used_in phrase` exists only when a
word's sense applies literally (e.g. *heavy rain*, not *kick the bucket*). A phrase's own meaning
lives under its own lexeme/sense, like any lemma.

Containing-phrase discovery (4.1.2) follows incoming `contains` from exact lexeme identities,
not substrings, forms or sense usage. For lemma targets, both visible `has_lexeme` edges and
visible lexeme endpoints are required. Phrase, component and relation owners are independently
authorized. Graph traversal uses existing relation adjacency and adds no schema/migration.
Pagination deduplicates phrase records before applying stored `text`, record-ID ordering,
offset and limit; concurrent graph changes can shift pages. Effective entries and original
source candidates are separate identities: private/custom phrases remain navigable without
being represented as shared offline add candidates. User text overrides do not change source keys.
Adding a phrase selects only its explicitly chosen own senses, not its component senses.
Repeat/cross-project adds reuse cards and never remove other project selections.

Task 4.1.1 materializes `contains` only for complete source-backed decompositions whose
components each resolve to a unique English word lexeme; unknown or ambiguous components
remain unlinked rather than being inferred from whitespace. `position` is zero-based, and
the deterministic edge ID is `[phrase lemma record, component lexeme record, position]`;
repeated component lexemes retain separate ordered edges. Shared source edges and endpoints
have `owner = NONE`. Offline component/usage records preserve source attribution; existing
`contains`/`used_in` schema has no extra provenance field.

Explicitly literal source associations produce `[component sense record, phrase lemma record]`
`used_in` IDs. The phrase's own selected senses remain separate from component senses.
Materialization is atomic and insert-only: repeat adds preserve existing shared content and all
user rows/edges; private deterministic-ID collisions fail rather than overwrite. Existing
owner-filtered record/edge reads independently authorize both endpoints and the edge, including
shared edges attached to foreign private endpoints. Migration `0005` already supports these
contracts and is unchanged; only the offline SQLite artifact advances to schema v2.

Dictionary field types: textual fields (including `source`, POS, CEFR and tag kind) are strings;
`freq_zipf` is a number; etymology number, ranks, orders and positions are integers; `common`
is boolean. String-list fields have typed string elements. Forms/pronunciations are typed object
arrays; pronunciation accents are `US | UK`, and optional audio is `record<media>`. Gloss and
translation are flexible objects with string-valued language keys, preserving languages beyond
`zh`. Fields marked `?` are optional (`NONE`, not `NULL`); `span` is exactly two integers.
Relation endpoint unions match the table above and are `ENFORCED`: endpoints must exist.
Phrase-only semantics for lemma endpoints remain a repository responsibility.

The dictionary migration adds the minimum unique `lemma(lang, text)` index. Its uniqueness is
global across owners, as specified above; custom lemma identity/ownership changes would need
a later forward migration. Relation endpoint traversal uses SurrealDB's graph storage; no
additional speculative lookup or edge-uniqueness indexes are introduced before repository queries
exist. In particular, different owners may attach edges to the same endpoints.

Scope: `media` metadata is listed under **Per-user tables**, not dictionary tables, and is
deferred to the media work. The pronunciation reference constrains its target table but does
not require a media record to exist. No media table/index, project, includes, override or note
schema is introduced by `0005`; sentence/passage and their edges are already present, so later
content tasks should reuse them rather than redefine this migration.

### Sentence and passage contract (4.2.1)

The existing immutable `0005_dictionary.surql` and committed snapshot satisfy the context
storage requirements; **no additional migration or duplicate definitions are needed**.
Sentence `text`, `lang`, `source` and string-valued multilingual `translation` are required;
an empty translation object is valid. Passage `title`, `text`, `lang` and `source` are required.
Both tables reject undeclared fields and accept shared or user ownership.

`used_in` remains sense → lemma/sentence/passage, with an omitted span allowed or an exact
two-integer array; `NULL`, fractional/boolean elements and other array lengths are rejected.
`part_of` remains sentence → passage with a required integer `order`, independent of insertion
order. Text/span bounds, semantic sense resolution, ordering policy, uniqueness/idempotency and
matching record/edge owners are repository/API obligations, not additional schema assertions.
In particular, an Alice-owned edge can reference Bob's existing private endpoint at the storage
level: checking only the edge owner is insufficient. Reads and writes must authorize both
endpoints as well as the edge; `ENFORCED` checks existence and table types, not authorization.

## Per-user tables

| Table | Fields | Notes |
|---|---|---|
| `user` | `username`, `password_hash`, `role` (admin\|user), `disabled`, `must_change_password`, `source_lang`, `target_lang`, `prefs {theme, locale, accent, desired_retention}` | |
| `refresh_token` | `user`, `token_hash`, `expires_at`, `revoked_at?`, `replaced_by?` | rotation |
| `project` | `owner`, `name`, `description`, `target_lang`, `source_lang`, `plan {daily_new, exam_date?, review_cap?}`, `created_at` | |
| `includes` (edge) | project → lemma\|lexeme\|sense\|sentence\|passage | `hidden`, `added_at`, `study_order?`. Selected senses = `includes` edges to senses. Lexeme edges are independent group-visibility markers, not sense selections. Hidden items are kept for restore and history |
| `override` | id `override:[user:<id>, <target record>]`, `fields` (partial object), `updated_at` | Edits per user, applied on read |
| `note` | `owner`, `target` (any record), `kind` (note\|mnemonic), `text` | |
| `media` | `owner?` (NONE for shared audio), `target`, `kind` (audio\|image), `path`, `mime`, `source` (wiktionary\|edge_tts\|pixabay\|upload), `attribution?`, `accent?` | |
| `memory` | id `memory:[user:<id>, <sense record>]`, `owner`, `sense`, FSRS card state (`card_id`, `state`, `step?`, `stability?`, `difficulty?`, `due`, `last_review?`), `introduced` | One per user and sense, shared across projects |
| `review_log` | `owner`, `memory`, `project`, `exercise`, `rating`, `auto_rating`, `correct`, `hint_used`, `duration_ms`, `at`, `is_introduction`, `attempt_id`, `request_fingerprint?`, `receipt?` | Completed reviews only; unique `(owner, attempt_id)` |
| `srs_optimization` | deterministic owner ID, last run/result, optional validated parameters and training metadata | One private row per user; no card/history mutation |
| `job` | `type`, `payload`, `status` (queued\|running\|done\|failed), `attempts`, `run_after`, `error?`, `owner?` | |
| `_migration` | id = version, `name`, `checksum`, `applied_at` | |

Migration `0013_memory_review_log.surql` adds two SCHEMAFULL normal tables, not relation
tables. Memory's required owner/sense references must match its array ID; `(owner, sense)`
is unique. `card_id` is the py-fsrs integer identifier (not the database ID and not globally
unique), `state` is Learning=1/Review=2/Relearning=3, and `step` is an optional nonnegative
integer. Stability/difficulty are optional floats; due and last_review are UTC datetimes.
These are all seven fields serialized by py-fsrs 6.3.0 `Card.to_dict()`/`from_dict()`;
convert datetime fields to/from ISO strings at that library boundary, and map absent
optional database fields to Python `None`. An unreviewed Learning card has step 0,
absent stability/difficulty/last_review and `introduced=false`. Queue reads must not
change that marker; the first completed review sets it and logs `is_introduction=true`.

Logs require an owner matching the owner component of their memory ID, both ratings
(Again=1/Hard=2/Good=3/Easy=4), correctness, hint use, a validated integer duration in
0..60,000 ms, exercise type string, UTC timestamp, project record reference and nonempty
opaque attempt ID. `(owner, attempt_id)` uniqueness prevents duplicate completed receipts;
atomic scheduling, conflicting-retry validation and stale-card handling belong to the
review service, not this migration. No attempt-table dependency is introduced.
Project references deliberately do not enforce existence or cascade: deleting a project
removes its memberships but preserves cards and completed history (including its original
project ID). Hiding/removing memberships also leaves cards and logs untouched.

Migration `0015_srs_preferences.surql` adds `user.prefs.desired_retention` (float,
0 < value < 1, default/backfill 0.9), without replacing the existing preferences object.
It adds internal `project.srs_revision` (integer, default/backfill 0); completed review
transactions increment it to serialize per-project limits across distinct cards. Public
project models deliberately omit this storage-only revision.
New logs additionally retain optional `request_fingerprint` and flexible `receipt` fields.
The fingerprint binds the immutable server grade, issuance card version, attempt/project/sense
and final rating. The receipt contains the complete resulting card and original completion
metadata; JSON UTC timestamps are restored by typed models. Fields are optional for older
logs; an old identity without a verifiable receipt is rejected rather than applied again.
The owner/attempt uniqueness index from `0013` remains the exactly-once identity constraint.
The FSRS 6.x wrapper round-trips all seven card fields through typed constructors, preserving
optional values and UTC precision. Only the first confirmed review flips `introduced`.

Migration `0006_project_overlays.surql` adds only `project`, `includes`, `override` and `note`.
All four are SCHEMAFULL with required `owner: record<user>` (no shared/NONE/NULL owners).
Project names, descriptions and languages are required strings; `plan` is a typed object with
required integer `daily_new`, optional datetime `exam_date`, and optional integer `review_cap`.
`created_at`, membership `added_at` and override `updated_at` are required datetimes, supplied
by callers; `hidden` is a required boolean, not deletion. Restore updates the same membership
edge, preserving its ID and `added_at`.

Add-to-project (`2.4.2`) creates new membership IDs as
`includes:[project:<id>, <target record>]`, with the project's owner, `hidden = false` and
the initial `added_at`. Targets are exactly the lemma plus explicitly selected senses;
lexemes have no memberships until a tree visibility update creates a group marker. A repeat reuses any existing matching owner/project/target
memberships (including legacy IDs), sets only their `hidden` flag to false, and preserves
IDs/timestamps. Omitted senses and their hidden flags remain untouched; additions accumulate
instead of replacing selections. No shared content, overrides or notes are rewritten; absent memory is created within the
same transaction without replacing an existing card.
Migration `0008_includes_lookup.surql` adds the nonunique `(owner, in, out)` lookup index;
deterministic IDs and the retryable add transaction prevent new duplicate memberships.

Migration `0012_project_tree_visibility.surql` extends the original `0006` endpoint union with
lexeme, preserving existing fields, indexes and edges. A missing lexeme marker means visible.
It also indexes the new tree relation lookups on `(in, owner, out)` for `has_lexeme` and
`has_sense`; memberships reuse `0008`'s owner/project/target index.
Hiding a lemma or lexeme changes only that ancestor's own flag; individual sense flags survive
ancestor hide/restore. A lexeme marker never selects unselected cached senses.
`includes` remains ENFORCED from an existing project to an existing target. Owners on projects, edges
and targets must each be checked by repositories: endpoint enforcement does not enforce matching
owners or authorization. No membership-uniqueness index is added by this task.

Override `fields` is a flexible partial object, preserving arbitrary nested values without
changing shared records. Repositories construct `override:[user, target]`, maintain its matching
`owner`, validate target visibility and permitted edit fields, and delete that owner-bound row
to reset; the database does not assert the ID shape or apply the overlay automatically.
There is no separate override `target` field. Note `target` is a required `record` of any table
(existence/visibility is checked by repositories), `kind` is `note | mnemonic`, and `text` is a
required string. The migration adds just `project_owner(owner)` and
`note_owner_target(owner, target)` non-unique indexes. Media remains a separate migration.

### Project API models and lifecycle

Migration `0016_project_sense_order.surql` adds optional nonnegative integer
`includes.study_order`. Existing memberships remain unchanged and initially sort by `added_at`
then edge ID; the owner-scoped reorder transaction writes contiguous positions across all
selected senses, including hidden items. Duplicate legacy edges receive the same target's
position. Hidden flags, membership IDs/timestamps, cards and history are not replaced.
New memberships without an explicit position append after persisted slots. The existing
owner/project/target lookup index serves these reads/writes; ordering is computed inside the
bounded snapshot. Reorder increments the existing internal project revision to serialize
concurrent reorders.

`ProjectCreate` requires `name` (trimmed, 1–128 characters). `description` defaults to `""`
(maximum 10,000 characters); `target_lang`/`source_lang` default to `en`/`zh` and accept trimmed
nonblank language strings up to 35 characters. `plan` defaults to
`{daily_new: 20, exam_date: null, review_cap: null}`. Daily-new and non-null review caps are
strict nonnegative signed 64-bit integers (zero is allowed); an exam date must include a timezone and is
normalized to UTC. The API rejects unknown fields, including client-supplied owner/ID/timestamps.

`ProjectUpdate` accepts those same fields, all optional; omitted fields stay unchanged, but
explicit top-level nulls are invalid. An empty patch is a no-op. Providing `plan` **replaces the
whole plan**, applying the create defaults for omitted plan members. Nested `exam_date` and
`review_cap` may be null to clear them (stored as database NONE, returned as JSON null).
`ProjectRead` returns `id` (opaque project rid), name, description, languages, complete plan,
and UTC `created_at`; owner is not exposed or mutable.

Deleting a project atomically removes its owner-bound `includes` edges (including hidden ones)
and the project itself. It never deletes dictionary/custom content, notes, overrides or another
project's memberships; reusable personal content survives. Since SurrealDB removes connected
relations when deleting an endpoint, inconsistent legacy data with another owner's membership
attached to this project is rejected with `409 project.membership_conflict`, leaving all rows
unchanged. Membership APIs must validate matching project/edge owners to prevent that state.

## Effective views

### Project tree HTTP contract (2.3.4)

Both routes require `current_user`, use opaque IDs and return `Cache-Control: no-store`:

| Route | Request → response |
|---|---|
| `GET /api/projects/{project_id}/tree` | `page=1`, `page_size=20` (1–100), `include_hidden=false` → `ProjectTreePage` |
| `PATCH /api/projects/{project_id}/tree/{table}/{target_id}/visibility` | `{hidden: boolean}` → `ProjectMembershipRead`; table is `lemma`, `lexeme` or `sense` |

`ProjectTreePage` contains `items`, `total`, `page`, `page_size`. Items are
`ProjectTreeLemmaRead(lemma, hidden, effective_hidden, lexemes)`, with
`ProjectTreeLexemeRead(lexeme, hidden, effective_hidden, senses)` and
`ProjectTreeSenseRead(sense, hidden, effective_hidden)`. Each content record uses
`DictionaryRecordRead` (stable `id`, `table`, `owner`, effective `fields`), including text,
POS, pronunciations/audio references, definitions, multilingual glosses and examples.
Only requester-owned overlays apply; content and both graph edges/endpoints are owner-filtered
inside the same SDK transaction as the selection read.

Only included lemmas and explicitly included senses participate. Normal reads omit hidden
lemmas and any sense hidden directly or by a lemma/lexeme ancestor. Groups with no remaining
selected visible senses are omitted; an included lemma with no such senses remains with
`lexemes=[]`. `include_hidden=true` is the restore-management interface: it retains hidden
selected nodes and groups, reports each node's own `hidden` plus inherited `effective_hidden`,
and still never exposes unselected senses. Lemmas/lexemes are ordered by opaque ID; senses
by effective rank then ID. Pagination/`total` count eligible lemmas, including empty ones.
Page numbers are bounded to signed 32-bit positive integers. Separate pages are separate
snapshots; concurrent membership changes may shift page positions.

Visibility updates require an own project and own, visible-target membership. Lexemes instead
require an owner-safe path from an included lemma to an included sense (hidden paths count).
They lazily create `includes:[project, lexeme]` markers. Updates restore the same edge IDs and
`added_at`, change no descendant flags and never rewrite dictionary rows, overlays, source
caches or another project's memberships. Legacy duplicate memberships are hidden if any
matching edge is hidden; an explicit update sets all matching own edges consistently without
deleting history. An existing foreign-owned deterministic marker yields 409
`project.membership_conflict`, not an ownership takeover.

The project UI paginates the restore-management response and distinguishes own `hidden` from
inherited `effective_hidden`. Its default view filters effective visibility without changing
membership; its hidden-management view can restore direct flags, and Undo sends the previous
own flag. Because pages count all included lemmas, a page can have no visible items even when
other pages or hidden items exist.

Each request admits at most 10,000 owner-visible memberships, 2,000 returned content nodes
per page and 2,000 matching edges per parent lookup. Oversized results fail explicitly with
413 `project.tree_too_large`; nothing is silently truncated. Request a smaller page for
page-level limits; membership limits require splitting the project. Missing/malformed/foreign
projects return 404 `project.not_found`; unavailable items return 404 `project.item_not_found`.
Visibility payloads reject unknown fields and non-boolean hidden values.

### Dictionary repository and service facade

API layers use `app.services.dictionary`, not database imports:

- `materialize_lemma(db, reader, text, *, lang="en", selected_senses=None)` returns
  `MaterializedDictionary(lemma_id, lexeme_ids, selected_sense_ids)`. `reader` is the typed async
  `LexiconReader`. Text/language use `lemma_key`; source lemma/lexeme/sense structured keys are
  retained unchanged. Returned IDs are canonical `encode_rid` transport strings, not record text
  or SQLite JSON strings. Explicit selections are **structured sense keys**, not transport IDs.
- `selected_senses=None` selects source `common` senses; `[]` selects no senses; an explicit list
  selects exactly those senses, deduplicated and returned in source lexeme/rank order. Every
  lexeme is materialized even when none of its senses is selected. Missing/foreign-lemma sense
  keys fail with `dictionary.invalid_selection` (422) before writes; an absent lemma is 404.
  Selection broadens the shared cache but never prunes previously materialized senses.
  `selected_sense_ids` describes this call, **not all cached senses**. Project add APIs must
  create their own owner-bound `includes` edges to these selected senses.
- `read_record(db, owner, rid, table)` returns `DictionaryRecordRead | None`;
  `read_records(db, owner, targets)` accepts `(table, rid)` pairs, preserves request order and
  omits missing/invisible targets. `owner` is the authenticated `user:<key>` subject.
- `read_entry(db, owner, lemma_id)` returns `DictionaryEntryRead | None`: an effective lemma and
  `DictionaryLexemeRead(lexeme, senses)` entries. It contains **all cached visible senses**,
  deduplicated and sorted by effective rank/ID, not a project's membership/hiding selection.
  The tree API must intersect this view with its owner-bound memberships.
- `read_edges(db, owner, rid, table, *, relation=None, direction="both")` returns sorted
  `DictionaryEdgeRead` neighbours. `relation` optionally selects any of the nine dictionary
  relation tables; direction is `incoming`, `outgoing` or `both`. Discovery/enrichment can use
  the endpoint IDs with `read_records`; no unrelated graph expansion occurs.

`DictionaryRecordRead` has `id`, bounded `table`, `owner` (subject or None), and `fields`
(JSON schema fields). `DictionaryEdgeRead` has `id`, `table`, `start`, `end`, `owner`, and
relation `fields`. Record-valued fields/endpoints also use encoded IDs. Effective reads use
one SDK transaction, independently filter both endpoint rows and relation ownership, and
apply only `override:[requester, target]` with matching owner. Overlay objects merge
recursively (e.g. language maps); arrays/scalars replace. Identity/ownership/unknown top-level
fields are ignored. These readers do not create, update or delete overlays or shared data;
the override API remains responsible for validating permitted field types on writes.

Materialization is atomic and insert-only: existing shared rows/edges, all user-owned rows and
all overrides remain unchanged. A deterministic identity occupied by user content causes 409
and rolls back the whole write rather than taking ownership. Shared edge IDs are
`<relation>:[start, end, ...identity]`; composition adds the position, semantic relations add
their type and source. This preserves repeated morphemes and distinct relation provenance.
No new schema/migration is needed.

### Lemma detail frontend (2.6.5)

The `word` route reads `DictionaryEntryRead` and treats its JSON `fields` as untrusted values,
mapping only checked strings, arrays and objects into shared presentation models. It does not
reconstruct effective values locally or infer project membership. Own override reads supply
customization markers; a missing override (404) is normal. Edits PATCH the selected target
without replacing unrelated overlay fields; Chinese gloss edits merge without deleting other
languages. Reset DELETE removes the complete own overlay and re-reads effective data.

Notes are queried and mutated for the selected visible lemma, lexeme or sense using generated
contracts. Saved annotations are server-backed and therefore survive project navigation and
reload. Unsaved note and mnemonic drafts use separate target/kind or existing-note keys in
owner-scoped tab session storage; they survive refresh/navigation, with an in-memory fallback
when storage is unavailable. Switching users clears the visible drafts before restoring that
owner's tab drafts. Frontend controls do not substitute for backend owner checks.

### Mnemonic suggestions (5.1.2)

`POST /api/notes/suggestions` accepts only `{target_table: lemma|lexeme|sense, target_id}`.
`GET /api/notes/suggestions/{job_id}` returns the caller's suggestion state. Both require
authentication, return `no-store`, and recheck target visibility. Responses are
`MnemonicSuggestion {status: pending|ready|unavailable, job_id?, text?, reason?}`.
The existing job stores only owner-bound target IDs/table and a content hash. Workers and
retrieval reject changed target/visible ancestry content. Suggestions use the existing
owner-scoped, prompt/schema/model/input-versioned `llm_cache`; even canonical shared targets
do not make mnemonic responses shared. No new schema or migration is needed.
Generation, rejection and acceptance create no notes. Acceptance changes only an editable
mnemonic draft; the existing notes POST/PATCH runs only on explicit Save. Ordinary notes keep
their identity and kind.

`lexemes[*].lexeme.fields.pron[*].audio` is an opaque media record ID. Protected media must be
fetched with bearer authentication, not assigned directly to an HTML audio source. The detail
page converts nonempty authenticated blobs into object URLs and disposes playback, requests
and URLs when leaving the lemma.

### User dictionary HTTP contract (2.3.3)

All routes below require an enabled, password-changed bearer user, return `Cache-Control:
no-store`, and use opaque record IDs. Missing, malformed, wrong-table and foreign-owned target
IDs return 404. Supported target tables are exactly `lemma`, `lexeme`, `sense`, `morpheme`,
`tag`, `sentence`, `passage`; project, user, relation and arbitrary-record annotations are not
exposed by this API, even though the note schema permits arbitrary record references.

| Route | Request → response |
|---|---|
| `GET /api/dictionary/lemmas/{lemma_id}/entry` | `DictionaryEntryRead` from `services.dictionary.read_entry` |
| `POST /api/dictionary/lexemes/{lexeme_id}/senses` | `CustomSenseCreate` → 201 `DictionaryRecordRead` |
| `GET /api/dictionary/{table}/{id}/override` | `OverrideRead` (404 if no own override) |
| `PUT /api/dictionary/{table}/{id}/override` | `OverrideUpdate` → `OverrideRead`; create or replace the entire own overlay |
| `PATCH /api/dictionary/{table}/{id}/override` | `OverrideUpdate` → `OverrideRead`; create or recursively merge the own overlay |
| `DELETE /api/dictionary/{table}/{id}/override` | 204; reset the entire own overlay, idempotent for a visible target |
| `POST /api/notes` | `NoteCreate` → 201 `NoteRead` |
| `GET /api/notes?target_table=...&target_id=...` | Own `NoteRead[]`, in ID order, for one visible target |
| `GET /api/notes/{id}` | Own `NoteRead` |
| `PATCH /api/notes/{id}` | `NoteUpdate` → own `NoteRead` |
| `DELETE /api/notes/{id}` | 204; subsequent access returns 404 |

`OverrideUpdate = {fields: OverrideFields}`. Only explicitly provided fields are stored/returned;
nulls, unknown fields and fields outside the target-specific allowlist return 422:

| Target | Editable fields |
|---|---|
| lemma | `text`, `cefr`, `exam_tags` |
| lexeme | `etymology_text`, `forms`, `pron` |
| sense | `definition`, `gloss`, `register`, `domain`, `examples`, `rank`, `common` |
| morpheme | `text`, `meaning` |
| tag | `name` |
| sentence | `text`, `translation` |
| passage | `title`, `text` |

Identity, owner, source/provenance, language, classification and structural pointers cannot be
overridden. Forms accept only `{form, tags}`; pronunciations accept only `{accent: US|UK, ipa}`,
never audio record pointers. Language maps have string values and language-tag keys. Text fields
are strict strings up to 10,000 characters, lists have at most 100 entries, `common` is a strict
boolean, and `rank` is a strict nonnegative signed 64-bit integer.
PATCH merges nested language maps; arrays/scalars replace. PUT discards omitted overlay fields,
so removing a single field means PUTting the remaining fields; `{fields: {}}` is a valid empty
overlay. DELETE removes the row. `OverrideRead` returns `target_table`, `target_id`, `fields`,
UTC `updated_at`, never the internal composite ID or mutable ownership.

`CustomSenseCreate` requires nonblank `definition`; optional `gloss`, `register`, `domain`,
`examples`, `rank`, `common` default to `{}`, `[]`, `[]`, `[]`, `0`, `false`. Its field types and
limits match the corresponding override fields. The server atomically creates a random-ID sense
with `source="custom"` and the authenticated owner, plus an equally owned `has_sense` edge to
the visible lexeme. It does not create memberships, modify shared rows, or materialize lexicon
data. Own custom senses are read through effective lemma entries and edited/reset through
overlays; another user's entry omits both the sense and its edge.

`NoteCreate = {target_table, target_id, kind?: note|mnemonic, text}`, with default kind `note`.
`NoteUpdate` accepts only optional `kind` and `text`; omitted fields stay unchanged, empty patches
are no-ops, nulls are rejected. Text is trimmed, nonblank and at most 10,000 characters.
`NoteRead = {id, target_table, target_id, kind, text}`. Notes cannot be retargeted or re-owned.
Every note operation rechecks target existence/visibility; knowing a note ID or having an
administrator role never grants access to another user's note. Visibility checks and writes
share a transaction. These endpoints reuse migration `0006`, without a schema change.

Supported source edges are `has_lexeme`, `has_sense`, affix `composed_of`, sense-domain
`member_of` (to `tag:['domain', normalized_name]`), and directional `relates_to`. Semantic
edges connect only already-materialized shared endpoints; incoming and outgoing source
relations are considered so either endpoint import order works, without importing unselected
or recursively related senses. The reader does not provide authoritative phrase-component,
literal-usage, derivation-edge, sentence or passage associations; this repository does not
guess `contains`, `used_in`, `derives_to` or `part_of`. Graph/content tasks must supply those
associations (including the phrase rule above); all nine edge types are already readable.
Pronunciations retain known US/UK IPA only: external audio metadata is not a `media` record
and is deferred to media ingestion. Source examples retain their text, Chinese glosses map to
`gloss.zh`, exam tags remain on the lemma, and absent source frequency maps to numeric 0.

- **Sense as seen by a user** = the shared sense record with `override:[user, sense].fields`
  merged on top. "Reset" deletes the override.
- **Project tree** = lemmas included in the project → their lexemes → senses that are included and
  not hidden, with overrides applied. Hiding a lemma or lexeme hides everything under it in that project.
- **All words** = the union of the user's non-hidden project contents plus their user-owned items.
  Edges are shown when both ends are visible.
- **Review queue for a project** = the user's `memory` rows for senses included (not hidden) in the
  project with `due <= now`, plus new senses up to the plan's daily limit.

## Per-user optimizer storage (7.1.5)

Forward-only migration `0024_srs_optimization.surql` adds the SCHEMAFULL record
`srs_optimization:[user:<id>]`. Its owner must match the identity, and a unique owner index
prevents duplicate state. `run_id`, `attempted_at` and flexible `result` describe the latest
attempt; optional `parameters`, `parameters_version`, `optimized_at`,
`parameters_fingerprint` and `trained_reviews` retain the last successful vector and its
py-fsrs/version, training time, input digest and qualifying-transition count. Failure or
insufficient history updates only the result, never this last good metadata. Stale run IDs
cannot overwrite a later claim.

The migration adds `(owner, last_review)` on memory. A single bounded recent-log scan uses
the existing `review_log(owner, at)` index, and checks both its owner and the referenced memory
owner. Optimization jobs contain no review history; training data passes
to the short-lived local process via a pipe. The scheduler revalidates the vector and version
inside each future review transaction, independently of `user.prefs.desired_retention`.

## Indexes (minimum)

`lemma(lang, text)` unique · `user(username)` unique · `project(owner)` · `memory(owner, due)` ·
`memory(owner, sense)` unique · `memory(owner, last_review)` · `review_log(owner, at)` ·
`review_log(owner, attempt_id)` unique · `srs_optimization(owner)` unique ·
`job(status, run_after)` · `note(owner, target)` ·
`media(target)` · `refresh_token(token_hash)` unique · `user(role)` (admin bootstrap) ·
`refresh_token(user)` (session revocation) · `refresh_token(expires_at)` (expiry cleanup).

Auth tables are introduced by `0002_auth.surql`. User fields are required, with no database
defaults; callers supply the flags, languages and complete preferences. Preferences have
`theme` = system/light/dark, a string `locale`, and `accent` = US/UK. Refresh tokens require a
`record<user>` reference, string hash and datetime expiry; `revoked_at` is an optional datetime,
and `replaced_by` an optional `record<refresh_token>`. These typed references constrain the
target table, not record existence. Only refresh-token hashes, never raw tokens, are stored.

### Media storage contract

`0007_media.surql` adds SCHEMAFULL `media`, independently of dictionary migration `0005`.
`target` is a typed record reference to lemma, lexeme, sense, morpheme, tag, sentence or
passage; `media_target(target)` indexes target lookup. `owner` is an optional user record
(NONE means shared). Required fields are `kind` (audio/image), safe relative `path`, MIME
and `source` (wiktionary/edge_tts/pixabay/upload); attribution and US/UK accent are optional.
References constrain table types, not existence. The media service additionally validates
kind/MIME/extension agreement, audio-only accent, target existence and visibility, and
filesystem containment. Paths are storage-only, never public metadata. API reads recheck
both owners and the current target rather than trusting media ownership alone.
