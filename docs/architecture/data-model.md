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
