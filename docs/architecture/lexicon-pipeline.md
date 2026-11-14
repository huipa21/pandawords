# Lexicon pipeline & enrichment

## Sources

| Source | Gives us | License / note |
|---|---|---|
| Wiktionary via kaikki.org (wiktextract English JSONL) | lemma → etymology/POS → senses, glosses, examples, IPA (US/UK tags), audio URLs, forms/inflections, derived/related terms, synonyms/antonyms, etymology templates (affixes) | CC BY-SA. Keep attribution on sense/media `source` and in exports |
| Open English WordNet (2025 WN-LMF XML, compatible with `wn`) | synonym/antonym/hypernym/hyponym relations, lexnames (concept tags) | CC BY 4.0 + inherited Princeton WordNet license; attribute both teams |
| ECDICT (skywind3000/ECDICT csv) | Chinese glosses, exam tags (`zk gk cet4 cet6 ky toefl ielts gre`), Collins/Oxford flags, BNC/COCA frequency, inflections (`exchange`) | MIT |
| wordfreq | Zipf frequency (used to pre-check "common" senses and band words) | Apache-2.0 / data CC BY-SA |
| spaCy `en_core_web_sm` | lemmatizing user input, sentences and passages | MIT |
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
   `memory` rows as new cards, and enqueue `enrich` and `audio` jobs.
4. **`enrich` job**:
   - materializes relations (`relates_to`, `derives_to`) between the new senses/lexemes and anything
     already materialized
   - attaches exam tags and frequency
   - later phases add phrases containing the word, morphemes and concept tags
5. **`audio` job** (per lexeme × accent): Wiktionary audio URL → download → `media`. If there is no
   recording, use edge-tts (`EDGE_TTS_VOICE_US` / `EDGE_TTS_VOICE_UK`) on the lemma text. Shared
   audio has `owner = NONE` and is generated once for all users.

## LLM (DeepSeek) uses — always optional

| Use | Cached where | Fallback |
|---|---|---|
| Scenario descriptions for scenario→word | `note`-like `generated` record on the shared sense (`owner = NONE`) | Exercise type skipped |
| Linking passage words to senses | `used_in` edge (`source='llm'`) | Most common included sense, marked `uncertain` |
| Mnemonic suggestions | user `note` (kind mnemonic), only when the user accepts | None |
| Morpheme decomposition when Wiktionary has no affix template | `composed_of` with `source='llm'` | None |

Rules: a stable system prompt prefix (for DeepSeek's automatic prefix cache), JSON output mode,
batching where possible, and a per-user daily request budget (setting).

## External fetch etiquette

- Wikimedia audio: set a descriptive User-Agent, cache permanently, throttle to ≤ 2 requests/s.
- Pixabay: images must be **downloaded and stored** (no hotlinking). Keep the attribution fields.
- Package sources: use the official ones first. Mirrors come from `.env` fallback variables.
