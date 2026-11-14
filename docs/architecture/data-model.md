# Data model (SurrealDB 3.3)

The source of truth for the current schema is `backend/app/db/schema.snapshot.json` (generated)
plus the migrations. This doc explains the intent. Syntax details: [../dev/surrealdb-notes.md](../dev/surrealdb-notes.md).

## Two layers

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

## Record IDs

Shared rows use deterministic IDs, so materialization is idempotent and imports merge cleanly:

| Table | ID |
|---|---|
| `lemma` | `lemma:['en', 'run']`, `lemma:['en', 'kick the bucket']` (normalized lowercase text) |
| `lexeme` | `lexeme:['en', 'run', 'verb', 1]` (lemma, part of speech, etymology number) |
| `sense` | `sense:['en', 'run', 'verb', 1, '<key>']`. `key` = source sense id if stable, else the first 12 chars of sha1(normalized gloss) |
| `morpheme` | `morpheme:['en', 'pre-', 'prefix']` |
| `tag` (shared) | `tag:[<kind>, <slug>]` |

User-created rows use random IDs (ULID strings).

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

Phrase rule: `contains` always exists, even for idioms. `sense used_in phrase` exists only when a
word's sense applies literally (e.g. *heavy rain*, not *kick the bucket*). A phrase's own meaning
lives under its own lexeme/sense, like any lemma.

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

## Per-user tables

| Table | Fields | Notes |
|---|---|---|
| `user` | `username`, `password_hash`, `role` (admin\|user), `disabled`, `must_change_password`, `source_lang`, `target_lang`, `prefs {theme, locale, accent}` | |
| `refresh_token` | `user`, `token_hash`, `expires_at`, `revoked_at?`, `replaced_by?` | rotation |
| `project` | `owner`, `name`, `description`, `target_lang`, `source_lang`, `plan {daily_new, exam_date?, review_cap?}`, `created_at` | |
| `includes` (edge) | project → lemma\|sense\|sentence\|passage | `hidden`, `added_at`. Selected senses = `includes` edges to senses. Hidden items are kept for restore and history but left out of the tree and reviews |
| `override` | id `override:[user:<id>, <target record>]`, `fields` (partial object), `updated_at` | Edits per user, applied on read |
| `note` | `owner`, `target` (any record), `kind` (note\|mnemonic), `text` | |
| `media` | `owner?` (NONE for shared audio), `target`, `kind` (audio\|image), `path`, `mime`, `source` (wiktionary\|edge_tts\|pixabay\|upload), `attribution?`, `accent?` | |
| `memory` | id `memory:[user:<id>, <sense record>]`, FSRS card state (`state`, `step`, `stability`, `difficulty`, `due`, `last_review`) | One per user and sense, shared across projects |
| `review_log` | `owner`, `memory`, `project`, `exercise`, `rating`, `auto_rating`, `correct`, `duration_ms`, `at` | |
| `job` | `type`, `payload`, `status` (queued\|running\|done\|failed), `attempts`, `run_after`, `error?`, `owner?` | |
| `_migration` | id = version, `name`, `checksum`, `applied_at` | |

Migration `0006_project_overlays.surql` adds only `project`, `includes`, `override` and `note`.
All four are SCHEMAFULL with required `owner: record<user>` (no shared/NONE/NULL owners).
Project names, descriptions and languages are required strings; `plan` is a typed object with
required integer `daily_new`, optional datetime `exam_date`, and optional integer `review_cap`.
`created_at`, membership `added_at` and override `updated_at` are required datetimes, supplied
by callers; `hidden` is a required boolean, not deletion. Restore updates the same membership
edge, preserving its ID and `added_at`.

`includes` is ENFORCED from an existing project to an existing lemma, sense, sentence or passage;
it does **not** accept lexeme endpoints. The tree API must derive ancestor visibility within this
contract; direct lexeme membership would require a later migration. Owners on projects, edges
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

## Effective views

- **Sense as seen by a user** = the shared sense record with `override:[user, sense].fields`
  merged on top. "Reset" deletes the override.
- **Project tree** = lemmas included in the project → their lexemes → senses that are included and
  not hidden, with overrides applied. Hiding a lemma or lexeme hides everything under it in that project.
- **All words** = the union of the user's non-hidden project contents plus their user-owned items.
  Edges are shown when both ends are visible.
- **Review queue for a project** = the user's `memory` rows for senses included (not hidden) in the
  project with `due <= now`, plus new senses up to the plan's daily limit.

## Indexes (minimum)

`lemma(lang, text)` unique · `user(username)` unique · `project(owner)` · `memory(due)` filtered by
user via ID prefix · `review_log(owner, at)` · `job(status, run_after)` · `note(owner, target)` ·
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
