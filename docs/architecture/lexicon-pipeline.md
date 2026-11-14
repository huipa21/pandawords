# Lexicon pipeline & enrichment

## Distractor consumers (3.2.2)

The learning service consumes already-materialized Phase 2 concept/domain tags and semantic
edges; it does not read the full SQLite lexicon or materialize extra words during selection.
Optional `morph_group` tags improve ranking but missing Phase 4 data is normal.
Fallback uses the selected lexeme's POS and the lemma's `floor(freq_zipf)` band; zero or absent
frequency is unknown, not a match. Existing shared/user ownership and per-user effective
overrides remain authoritative. There is no LLM or fabricated-candidate fallback.

## Sources

| Source | Gives us | License / note |
|---|---|---|
| Wiktionary via kaikki.org (wiktextract English JSONL) | lemma → etymology/POS → senses, glosses, examples, IPA (US/UK tags), audio URLs, forms/inflections, derived/related terms, synonyms/antonyms, etymology templates (affixes) | CC BY-SA. Keep attribution on sense/media `source` and in exports |
| Open English WordNet (2025 WN-LMF XML, compatible with `wn`) | synonym/antonym/hypernym/hyponym relations, lexnames (concept tags) | CC BY 4.0 + inherited Princeton WordNet license; attribute both teams |
| ECDICT (skywind3000/ECDICT csv) | Chinese glosses, exam tags (`zk gk cet4 cet6 ky toefl ielts gre`), Collins/Oxford flags, BNC/COCA frequency, inflections (`exchange`) | MIT |
| wordfreq | Zipf frequency (used to pre-check "common" senses and band words) | Apache-2.0 / data CC BY-SA |
| spaCy + `spacy-lookups-data` English lookup pipeline | offline lemmatizing of candidate input; contextual sentence/passage models deferred | MIT |
| lemminflect | inflection fallback when Wiktionary forms are missing | MIT |

Field names in kaikki and ECDICT must be checked against the real files in task 2.1.x. Record them in
`backend/scripts/README.md`.

## Download, offline build and release (`dev.ps1 lexicon`)

```
download → data/lexicon/raw/   (kaikki .jsonl, ecdict.csv, OEWN .xml.gz; manifest.json)
build    → data/lexicon/lexicon.sqlite   (read-only at runtime)
package  → dist/pandawords-lexicon-yyyy-MM-dd.tar.gz + .tar.gz.sha256
```

Downloads are independent of the builder: from `backend`, run
`uv run --no-sync python -m scripts.download_lexicon <kaikki|ecdict|oewn>`.
The default raw directory belongs to the main worktree and is shared, gitignored data.
Official sources are always attempted before an explicitly supplied `--fallback-url`.
The manifest records URLs/origin, version or UTC retrieval date, licenses, exact-byte SHA-256,
size and available HTTP metadata. OEWN 2025 is pinned to the official release asset checksum;
mutable sources can be pinned with `--sha256`. Cached files are verified offline, never silently
overwritten; missing files must still match their existing manifest. Complete payload validation
and staged publication prevent failed transfers from becoming final artifacts. A directory lock
serializes shared manifest updates. Use a separate `--raw-dir` for intentional snapshot upgrades.

Observed fields, exact source URLs, licenses, recovery instructions and commands are in
[`backend/scripts/README.md`](../../backend/scripts/README.md). Bounded upstream checks on
2026-11-14 confirmed the ECDICT CSV header, English wiktextract records and OEWN 2025 WN-LMF XML.
The English-only kaikki endpoint is deprecated upstream; the proposed raw replacement is
multilingual, so it must not be silently substituted. Full dataset downloads are not test inputs.
The core SQLite builder is available as `uv run --no-sync python -m scripts.build_lexicon`
from `backend`. `dev.ps1 lexicon` orchestrates the verified downloader and the ordered
ECDICT → wordfreq → OEWN hooks, never disabling enrichment implicitly. Both main and linked
worktrees share the main worktree's ignored raw data, SQLite output and `dist`. Explicit
`-RawDir`, `-Output`, `-DistDir` and `-Date` flags isolate snapshots without editing `.env.dev`.
The Python entrypoint is `python -m scripts.lexicon_release` with corresponding
`--raw-dir`, `--output`, `--dist-dir` and `--date` options.

The release archive contains exactly `lexicon.sqlite`, `manifest.json` and `SHA256SUMS`.
The manifest preserves download records and all database source attributions, including
wordfreq's installed version, plus database schema version, SHA-256, size and build counts.
Internal checksums cover SQLite and the manifest; an adjacent archive-specific `.sha256`
covers the compressed transfer bytes without changing application-release `SHA256SUMS`.
No raw datasets or private environment files are packaged; the lexicon remains outside site
backups. Publication uses private sibling stages and exclusive atomic hard links (the target
filesystem must support them), with the archive published last as the completion marker.
Existing archives/sidecars are refused, and a mismatched existing database is never replaced.
Failures report `prepare`, `download:<source>`, `build`, `package` or `publish`, exit nonzero
and remove private stages/new outputs; successfully downloaded raw inputs remain cached.
Concurrent builds of the same output directory are refused by a release lock.

- `lexicon.sqlite` tables: `lemma`, `lexeme`, `sense`, `pron`, `form`, `relation`, `zh_gloss`,
  `exam_tag`, `freq`, `affix`, plus `form_index(form → lemma)` for inflection lookup.
- The build streams the input (orjson, line by line) so it stays within the server's 4 GB RAM. It
  normally runs on the laptop. The artifact is transferred to the server as
  `pandawords-lexicon-<date>.tar.gz` and mounted read-only.
- SQLite schema v1 (`PRAGMA user_version=1`) uses compact JSON arrays from the shared
  `app.domain.dictionary_keys` helpers as lemma/lexeme/sense TEXT primary keys. `source` holds
  attribution and input metadata; per-row source references preserve provenance. Inflection
  lookup includes normalized lemma spellings, forms and explicit `form_of` backlinks. US/UK
  IPA and source audio metadata are retained without downloading media.
- A build uses a unique sibling stage and replaces the final file only after import,
  enrichment, integrity/foreign-key checks and commit succeed. Invalid records fail with line
  numbers; individual senses lacking usable glosses are counted/skipped. An empty usable
  lexicon is an error. JSONL lines are limited to 16 MiB, SQLite's page cache to 8 MiB; source
  data is never accumulated in memory.
- ECDICT/wordfreq and OEWN are independent enrichment modules. The builder's ordered
  `enrichers` callables receive the writable `sqlite3.Connection` after core import, before
  validation/atomic publication. They populate the predeclared enrichment tables without
  changing core transforms or schema. Exact columns, IDs, JSON encoding, constraints,
  reader lookups and callable/CLI contracts are in
  [`backend/scripts/README.md`](../../backend/scripts/README.md#sqlite-v1-and-extension-contract).
- Senses are aligned across sources: Wiktionary is the backbone. ECDICT Chinese glosses attach at
  POS level (`sense.gloss_zh` for the top sense, `zh_gloss` lexeme-level list otherwise). OEWN
  aligns only existing lemma/POS senses, using the maximum pairwise gloss token Jaccard
  score across all Wiktionary glosses and OEWN synset definitions. Tokens are NFKC/case-folded
  Unicode alphanumeric words, with the fixed stopword list recorded in source metadata.
  A score **>= 0.30** selects the best sense; ties prefer etymology number, sense rank, then ID.
  Below 0.30 (including missing/empty definitions), the first etymology's top sense is used.
  Relations have `source='oewn:approx'` if **either** endpoint uses that fallback.
  Same-synset members produce both synonym directions; explicit sense/synset relations retain
  their supplied direction and only synonym/antonym/hypernym/hyponym types are admitted.
  Missing lemma/POS/synset/target mappings and self-edges are skipped, never materialized as
  placeholders. OEWN `lexfile` fills an aligned sense's empty `lexname`; existing values and
  domain tags are preserved (first source-order assignment wins if several synsets converge).
  Three streaming XML passes retain only matched identities/alignments, not the XML tree or
  full source relation graph. Plain XML and the downloaded gzip artifact are supported without
  installing `wn`; source records retain OEWN and Princeton attribution and input checksum.
- Test fixture: `backend/tests/fixtures/lexicon_small.sqlite`, exactly 50 lemmas (52 input
  records) covering polysemy, phrases, US/UK differences and derivation etymology. Rebuild
  offline from `backend` with `uv run --no-sync python -m scripts.build_fixture_lexicon`.
  The committed `lexicon-small.words`, `.jsonl`, `-ecdict.csv`, `-oewn.xml` and
  `-frequency.json` files in `tests/fixtures` are curated **synthetic test data**, not upstream
  extracts or authoritative dictionary/frequency claims. The wrapper calls the production
  `build(..., words=..., enrichers=...)` with the production ECDICT, frequency and OEWN hooks.
  Frequency uses an explicit synthetic snapshot/version, not a machine-dependent wordfreq
  installation. Source names identify the parser/enricher; input hashes retain provenance.
  Rebuilds preserve logical data; byte-identical SQLite files are not guaranteed.
  `decide → decision` is represented by production-imported `affix` rows on the `decision`
  lexeme: position 0 is root/base lemma `decide`, position 1 is suffix `-ion`. The template's
  `alt1=decis` is display text, not the base identity. Typed reader tests resolve that root
  back to the `decide` lemma/verb lexeme; no fixture-only SQL fabricates the relationship.
  The importer conservatively supports English `suffix`/`suf` templates with exactly one
  base and suffix. It skips malformed, non-English, multi-component, markup-containing and
  conflicting decompositions rather than guessing. This uses the existing affix schema,
  not a new semantic relation type; `relates_to` and later graph materialization are separate.

### Runtime reader

`app.services.lexicon.LexiconReader(path: Path)` is an async read-only boundary for repositories,
candidate selection and jobs. Pass the configured artifact path explicitly; it neither loads
environment files nor imports build scripts. Call `await reader.validate()` at startup to check
schema v1, required columns, integrity, foreign keys and nonempty senses.

All public reads are async and return `app.domain.lexicon` pydantic records, never SQLite rows,
cursors or connections. Lemma/lexeme/sense IDs and foreign IDs are shared `DictionaryKey`
lists (`list[str | int]`), decoded from the storage representation; callers can pass the
existing `lemma_key`, `lexeme_key` and `sense_key` results directly. Pronunciation IDs remain
opaque strings. `LexiconSense.registers` holds source register labels.

| Reader method | Result |
|---|---|
| `get_lemma(text, *, lang="en")`, `get_lemma_by_id(key)` | `LexiconLemma \| None` |
| `lookup_form(text, *, lang="en")` | `list[LexiconLemma]` (all matching normalized inflections/phrases) |
| `get_lexeme(key)`, `lexemes(lemma_id, *, pos=None)` | optional `LexiconLexeme` / list |
| `get_sense(key)`, `senses(lexeme_id, *, common_only=False)` | optional `LexiconSense` / ranked list |
| `pronunciations(lexeme_id, *, accent=None)`, `forms(lexeme_id)` | `list[LexiconPronunciation]` / `list[LexiconForm]` |
| `relations(sense_id, *, type=None, direction="outgoing")` | `list[LexiconRelation]`; incoming does not reverse stored endpoints |
| `glosses(lexeme_id)`, `tags(lemma_id)`, `frequencies(lemma_id)` | `list[LexiconGloss]` / `list[LexiconTag]` / `list[LexiconFrequency]` |
| `affixes(lexeme_id)`, `sources()` | `list[LexiconAffix]` / `list[LexiconSource]` |
| `affixes_for_root(text, *, lang="en")` | `list[LexiconAffix]`; normalized exact root backlinks, language-filtered |

Exact lemma lookup does not fall back to inflections; use `lookup_form` explicitly. Text
lookups use canonical normalization, IDs are exact, and all collections have deterministic
ordering. Absent records return `None`/`[]`. Missing/invalid artifacts raise `AppError` with
`lexicon.missing` / `lexicon.invalid` (503), including at read time. SQLite/JSON/model validation
errors do not escape the service. Reads use bound values and worker-thread-local connections
with URI `mode=ro` and `query_only=ON`; no write API exists. Every operation closes its connection,
so no lifecycle/close call is required and readers do not hold files open between operations.

### ECDICT/wordfreq selection (2.1.3)

The builder's independent `--ecdict PATH` / `--wordfreq` / `--oewn PATH` flags opt into offline
enrichment. The release command always enables all three, in that order.
The typed `ecdict_enricher(path)` and `wordfreq_enricher()` factories expose callable hooks
and result counters for fixture/release orchestration. Missing requested sources fail explicitly;
neither flag implies a download. ECDICT attribution includes the CSV checksum/verified manifest;
wordfreq attribution includes the locked package/data version and licensing.

ECDICT matches normalized English lemma spelling exactly. POS-prefixed Chinese translations
need a unique matching lexeme; an unlabeled translation needs a unique lexeme overall.
Unknown POS, missing lemma/POS and multiple etymologies are logged and counted, not guessed.
The first distinct aligned gloss becomes the primary translation on the lexeme's top sense;
other Chinese glosses remain lexeme-level. This is a documented top-sense approximation, not
a bilingual semantic alignment. Duplicate normalized CSV words use the first source row;
glosses and recognized exam tags are deduplicated. BNC/COCA ranks retain ECDICT provenance.

wordfreq supplies English `best` Zipf values, synchronized between `lemma.freq_zipf` and its
own `freq` row (zero means unknown). For each lexeme, **Zipf >=5 selects two top senses**;
**3 <= Zipf <5 selects one**; lower/missing values select none. An aligned primary ECDICT
gloss additionally selects its top sense regardless of frequency. Ranking uses `(rank, id)`,
so ties are deterministic. Both hooks recompute these flags; either hook order yields the
same selection, with no selection from unresolved glosses. The full parser, result/logging
and source contracts are in the scripts README's ECDICT/wordfreq section.

## Add-word flow

1. **Input** → normalize → spaCy lemma plus `form_index` lookup. "went" → `go`; multi-word input
   is looked up as a phrase lemma first.
2. **Candidates API** returns the lemma's lexemes and senses from `lexicon.sqlite`. Senses marked
   `common` are pre-checked (top-ranked senses per POS with frequency weighting, plus any sense
   matching ECDICT's primary gloss).
3. **Add** → materialize the chosen lemma/lexeme/senses into the shared dictionary (idempotent
   upsert by deterministic ID). Create `includes` edges for the lemma and selected senses, create
   enqueue `enrich` and `audio` jobs. New `memory` cards are deferred to the SRS tasks;
   add-to-project does not create or reset review state.
4. **`enrich` job**:
   - materializes relations (`relates_to`, `derives_to`) between the new senses/lexemes and anything
     already materialized
   - attaches exam tags and frequency
   - later phases add phrases containing the word, morphemes and concept tags
5. **`audio` job** (per lexeme × accent): Wiktionary audio URL → download → `media`. If there is no
   recording, use edge-tts (`EDGE_TTS_VOICE_US` / `EDGE_TTS_VOICE_UK`) on the lemma text. Shared
   audio has `owner = NONE` and is generated once for all users.

### Add-to-project contract (2.4.2)

`POST /api/projects/{id}/dictionary` requires an enabled, password-ready bearer user.
`id` is the project's opaque API ID. Request example:

```json
{"lemma_key":["en","run"],"selected_senses":[["en","run","verb",1,"run-move"]]}
```

Use the structured `lemma.id` and `sense.id` arrays from candidates, not opaque database IDs.
Both fields are required; `selected_senses: []` adds only the lemma. Keys must be canonical
English identities, and every selected sense must actually belong to that lemma in the
configured typed `LexiconReader`. Duplicate keys are collapsed by materialization.
Unknown lemmas return `404 dictionary.not_found`; invalid selections return
`422 dictionary.invalid_selection`. Missing, malformed and foreign projects all return
`404 project.not_found`, without changing dictionary rows or enqueueing jobs.

The `200` response has `project_id`, opaque `lemma_id`, `lexeme_ids`,
`selected_sense_ids`, `membership_ids`, and `jobs` (`JobRead`: `id`, `type`, `status`,
`attempts`, `run_after`, `error`). The selected IDs describe this request, not the project's
whole accumulated selection. Membership IDs use the same opaque record transport.
Returned job IDs are readable only by the requester through `GET /api/jobs/{id}`.
Responses are `Cache-Control: no-store`.

The owner check, insert-only shared materialization, membership changes and job enqueues
share one retryable database transaction. Enqueue failure rolls everything back. No LLM,
audio download, TTS or other external work runs in the request. Repeating an add restores
only the lemma and explicitly selected senses; it does not deselect or unhide omitted
senses, reset timestamps, modify notes/overrides or alter review state.

Worker payload models live in `app.domain.add_to_project`:

- `EnrichJobPayload`: `{version: 1, lemma_key, lemma_id, lexeme_id, sense_id}`.
  One `enrich` job per selected sense.
- `AudioJobPayload`: `{version: 1, lemma_key, lemma_id, lexeme_id, accent: "US" | "UK"}`.
  One `audio` job per materialized lexeme and accent, including lexemes without selected
  senses (the materializer always imports the lemma's lexemes).

Payload record IDs are opaque transport strings; `lemma_key` remains the structured
candidate identity for source lookup. Jobs belong to the requester, while dictionary rows
and eventual audio remain shared. `jobs.enqueue(..., dedup_key=..., txn_id=...)` reuses a
job for `(owner, type, dedup_key)`, including running/done/failed jobs without resetting
attempts or status. Keys are `dictionary:v1:sense:{sense_id}` for enrichment and
`dictionary:v1:lexeme:{lexeme_id}:{accent}` for audio. Thus repeat/subset requests and other
projects of the same owner reuse jobs. Different owners get independently readable jobs;
future audio handlers must still reuse shared media across users.
The `audio` handler is registered in `app.worker.handlers.HANDLERS`, additively alongside
other handlers. Dispatch supplies the active database and configured settings through
`app.worker.context.get_context()`; `app.services.audio.acquire(db, settings, reader,
AudioJobPayload)` is the explicit service interface.

### Shared audio contract (2.5.2)

The worker validates that payload IDs name a shared lemma/lexeme pair. It first looks for
shared `media` targeting that lexeme and accent, validates its local file through the media
service, and reuses it across requester-owned jobs. Missing cached files trigger acquisition
again. Wikimedia recording candidates must match the requested accent; ambiguous/untagged
recordings are not guessed. Commons `imageinfo` resolves the original recording URL, MIME,
artist/credit and license metadata. Only HTTPS `upload.wikimedia.org/wikipedia/commons/`
downloads are accepted; redirects, unsupported MIME, empty and oversized files are rejected.
Stored attribution includes the file URL, upstream credits and available Commons license
metadata, never an assumed blanket recording license.

If a recording is absent or permanently unavailable, optional Edge TTS synthesizes the
lemma using the configured accent voice. A blank voice or explicit no-audio result logs an
unavailable event and completes the optional job without media. Timeouts, transport failures,
HTTP 429/5xx and unexpected exceptions remain worker failures and use its bounded retry
policy; a transient recording failure retries before replacing it with synthetic audio.
No failure changes the already-committed add operation.

Both providers write only through `media.store`, with `owner = NONE`, target `lexeme`,
kind `audio`, accent, source `wiktionary`/`edge_tts`, MIME and attribution. Attachment updates
the shared lexeme's existing `pron[*].audio` record reference while preserving IPA. When no
IPA exists, an accent entry with `ipa: ""` is added (not a fabricated transcription).
Effective entry reads encode `lexemes[*].lexeme.fields.pron[*].audio` as an opaque media ID.
The detail UI can use that ID with authenticated `GET /api/media/{id}`; metadata comes from
`media.read(db, settings, id, user)` for internal callers. No local path or external URL is
used for playback, and no API model/schema change or regenerated API types is needed.
`enrich` is registered alongside `audio` in the production worker registry.
Add-to-project itself only persists work and exposes its status.

Listening recall (3.2.4) reads these existing effective `pron[*].audio` IDs without enqueuing
or acquiring audio. Before returning a prompt it authorizes the media and local file, checks
the exact lexeme target and preferred accent, and derives the spoken spelling from the
canonical stored lemma (both recording and TTS workers speak that headword). An unrelated
effective headword override or another inflection must not silently change the audio's answer.
Absent, inaccessible or broken recordings make listening unavailable, not the whole queue.
Playback continues through authenticated `/api/media/{id}` with no filesystem/provider URL
in the prompt. No schema or media-delivery API changes are needed.

### Enrichment worker contract (2.4.3)

`app.worker.enrich.enrich(Job)` validates the v1 `EnrichJobPayload`, obtains the dispatch's
database/settings via task-local `worker.context.get_context()`, constructs the configured
typed reader and calls `services.enrichment.enrich(db, reader, payload)`. `execute`/`run_once`
accept optional keyword-only `settings`; `run_worker` passes its actual settings. Existing
Job-only custom handlers still work, and context is reset after success/failure/cancellation.

Payload lemma/lexeme/sense identities must match the reader's source lineage and already
exist as shared rows. Enrichment never creates related senses, lexemes or user-owned items.
It reuses dictionary relation projection and insert-only graph materialization in one retryable
transaction. Incoming/outgoing semantic edges retain their exact stored type, direction and
`source`, including `oewn:approx`; deterministic edge identity includes source and type.
Missing/private optional endpoints are skipped, while occupied private anchor/edge identities
fail without modifying them. Requester jobs remain owner-scoped; imported edges have `owner = NONE`.

Conservative derivation uses the production affix reader, not guessed morphology: exactly one
root plus modifiers, consistent source attribution, and exactly one source base lexeme are
required. It adds base → derived `derives_to` with source and modifier text in `via`; reverse
root lookup also handles a base added after its derived item. Ambiguous/missing bases are logged.
Neither endpoint is imported by enrichment.

Typed frequency rows attach to `lemma.frequencies` (source, Zipf, BNC/COCA ranks); a unique
available Zipf updates `freq_zipf`. Conflicting Zipf values are retained with provenance but
logged instead of guessed. Exam tags attach as `exam_tags` plus `exam_tag_sources` (tag/source).
Migration `0010` adds these optional provenance fields and `derives_to.source`.
Absent optional source collections are explicitly logged and leave existing metadata unchanged;
missing/invalid artifacts and database failures propagate into the worker's scheduled retries.
Only shared metadata changes: per-user overrides, notes, memberships and custom edges are untouched.

### Candidates contract (2.4.1)

`POST /api/dictionary/candidates`, bearer-authenticated, takes exactly `{"text":"went"}`.
Input is English, 1–200 characters before normalization, then NFKC/case-folded with collapsed
whitespace. Blank, non-string, punctuation-only/numeric-only, hidden control characters and
unknown body fields fail with `422 validation.invalid`. Whitespace separators are permitted.
Authentication uses the normal enabled-user/password-change gates (401/403).

The 200 response is `{normalized, candidates, sources}` with `Cache-Control: no-store`.
Each candidate has the full typed `lemma`, `matched_by` (`exact`, `form`, `spacy`) and
`lexemes`. Each lexeme entry contains `{lexeme, senses, pronunciations, glosses}`.
Structured lemma/lexeme/sense IDs are retained for add-to-project selection; senses retain
their rank, `common` preselection flag, bilingual definitions, examples and source/source_id.
`sources` contains the lexicon attribution records with licenses/version/checksums. Candidate
data is shared, not user-owned, and contains no personal membership or override data.
Unknown words/phrases return `candidates: [], sources: []`, not 404.

Exact matches come first, followed by every `form_index` result, deduplicated by lemma ID.
If a single-word input has no exact match, spaCy's lemma and its form-index matches are
appended without discarding existing candidates. Phrases are atomic: exact phrase and
phrase-form lookups only, never separate per-token guesses. Lexemes/senses retain reader order.

The production dependency `app.api.dependencies.get_lexicon_reader` uses
`Settings.lexicon_path` (`LEXICON_PATH`) when supplied, otherwise
`Settings.lexicon_dir / "lexicon.sqlite"` (`LEXICON_DIR`). Paths resolve against the API
process's working directory; use absolute paths for fixture-backed servers/E2E, for example
`C:\other\pandawords\backend\tests\fixtures\lexicon_small.sqlite`. Tests can construct
`create_app(settings.model_copy(update={"lexicon_path": fixture_path}))`; no private env
edit, dictionary download or reader mock is required. Missing/invalid artifacts return
`503 lexicon.missing` / `503 lexicon.invalid` lazily on candidate reads, leaving health,
OpenAPI and unrelated routes available.

Python 3.14 uses locked spaCy 3.8.18 (verified `cp314-win_amd64` wheel) with
`spacy.blank("en")` + lookup-mode lemmatizer and locked `spacy-lookups-data` 1.0.5.
No statistical model, model download, LLM or network request is needed at runtime.
Pipeline creation/initialization and inference both run in `asyncio.to_thread`, protected by
a worker-side lock and cached once per process. Lookup is deterministic but not contextual
POS disambiguation; form-index ambiguity is preserved. Contextual sentence/passage tagging
and its separate model selection remain later work.

## LLM (DeepSeek) uses — always optional

| Use | Cached where | Fallback |
|---|---|---|
| Scenario descriptions for scenario→word | `note`-like `generated` record on the shared sense (`owner = NONE`) | Exercise type skipped |
| Linking passage words to senses | `used_in` edge (`source='llm'`) | Most common included sense, marked `uncertain` |
| Mnemonic suggestions | owner-scoped `llm_cache`; user `note` (kind mnemonic) only on explicit Save | Manual mnemonic editing |
| Morpheme decomposition when Wiktionary has no affix template | `composed_of` with `source='llm'` | None |

Rules: a stable system prompt prefix (for DeepSeek's automatic prefix cache), JSON output mode,
batching where possible, and a per-user daily request budget (setting).

Mnemonic suggestions are explicit worker jobs, not an enrichment or page-load side effect.
Only canonical target text/POS/forms/definition/gloss and visible canonical ancestry needed
to identify the word are sent; notes, personal overrides and unrelated context are excluded.
Job payloads carry IDs and a versioned content key, never note text. Plain-text output
(1–2000 characters) is validated before caching and again on cache reads. Budget, disabled,
provider and timeout failures leave the user's editable draft unchanged. Accepting a suggestion
fills a draft (with replacement confirmation), not a persistent note.

## External fetch etiquette

- Wikimedia audio: set a descriptive User-Agent, cache permanently, throttle to ≤ 2 requests/s.
  `WIKIMEDIA_USER_AGENT` applies to both Commons metadata and recording downloads.
  `WIKIMEDIA_REQUEST_INTERVAL_SECONDS` defaults to 0.5 and cannot be configured lower.
  Throttling is shared by all audio jobs in a worker process; multiple worker processes
  must be operated with a combined Wikimedia request rate ≤ 2/s.
- Pixabay: images must be **downloaded and stored** (no hotlinking). Keep the attribution fields.
- Package sources: use the official ones first. Mirrors come from `.env` fallback variables.
