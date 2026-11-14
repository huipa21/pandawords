# Lexicon scripts

## Download independently

From the repository root in PowerShell (Python 3.14; existing backend dependencies):

```powershell
Set-Location backend
uv run --no-sync python -m scripts.download_lexicon kaikki
uv run --no-sync python -m scripts.download_lexicon ecdict
uv run --no-sync python -m scripts.download_lexicon oewn
```

Default output is the **main worktree's** ignored `data\lexicon\raw\` (resolved through
`git rev-parse --path-format=absolute --git-common-dir`), shared by task worktrees.
`--raw-dir <path>` explicitly overrides it. Nothing is imported into the application or database.

Each invocation tries the official URL first. Optionally supply
`--fallback-url https://your-mirror.example/same-artifact`; it is tried only after an HTTP,
network, checksum or payload-validation failure. The mirror must provide the same format,
language and release, not a zip/HTML landing page. There is no implicit mirror or environment
configuration. HTTPS URLs must not contain credentials.

`--sha256 <64-lowercase-hex-digits>` pins a trusted checksum, useful for mutable kaikki/ECDICT
URLs. OEWN 2025 is already pinned to its official GitHub release asset SHA-256:
`9ca6d1dcb75f822fdd66617f7d9da48142ace38dd544d6ad5e2feca1674ad3fe`.
Without an upstream/user pin, the first download establishes a local checksum, not independent
proof of upstream authenticity.

`manifest.json` has `schema_version: 1` and an `artifacts` object keyed by
`kaikki`, `ecdict`, `oewn`. Records include filename, official/requested/resolved URL,
official/fallback origin, version (OEWN: `2025`; mutable sources: null), UTC retrieval date,
license and license URL, SHA-256, byte count, ETag and Last-Modified when supplied.
Checksums refer to exact stored bytes, including gzip compression.

Reruns verify cached size/checksum without contacting the network. A mismatched or unrecorded
existing file is an error, never silently replaced. If a recorded file is missing, its replacement
must match the recorded checksum, even from a mirror. For a deliberate new release/snapshot,
use a separate `--raw-dir` and retain the old manifest; there is no destructive refresh flag.
The directory lock prevents concurrent manifest writers across worktrees. After a hard process
termination, verify no downloader is running before manually removing `.download.lock` and
abandoned hidden `.part` files. Ordinary failures clean stages and release their own lock.
Only complete, format-validated payloads become final files; errors identify the source and URL.

## Upstream observations (2026-11-14)

Verified official metadata and bounded HTTP reads; no full datasets were downloaded for tests:

- **kaikki**: official
  `https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl`
  is English-only, one JSON object per line. A bounded 1 MiB read included the first complete
  entry (`dictionary`): `word`, `lang`, `lang_code` (`en`), `pos`, `senses`, `sounds`, `forms`,
  `etymology_text`, `etymology_templates`, `etymology_links`, `head_templates`, `hyphenations`,
  `synonyms`, `hypernyms`, `hyponyms`, `meronyms`, `related`, `derived`, `coordinate_terms`,
  `descendants`, `translations`. Its first sense had `glosses`, `examples`, `id`, `links`,
  `categories`, `attestations`, `coordinate_terms`, `hypernyms`; first sound: `ipa`, `tags`;
  first form: `form`, `tags`. These are observations, not required fields on every entry.
  The source page reported extraction 2026-10-30 from the 2026-10-01 Wiktionary dump.
  This English-only postprocessed endpoint is **deprecated** upstream. Its proposed raw
  replacement contains hundreds of languages (24.8 GB), so do not silently substitute it;
  migration needs an explicit English-filtering decision. License: Wiktionary CC BY-SA 4.0;
  preserve attribution and consult linked copyright terms, including imported text/media.
- **ECDICT**: official
  `https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv`;
  a bounded 16 KiB read confirmed the header:
  `word,phonetic,definition,translation,pos,collins,oxford,tag,bnc,frq,exchange,detail,audio`.
  CSV quoting matters; use `csv`, not comma splitting. `translation` supplies Chinese glosses,
  `tag` exam labels, `exchange` inflections, `bnc`/`frq` frequency ranks. License file: MIT.
- **OEWN**: official GitHub latest-release API reported `2025-edition`; use its
  `english-wordnet-2025.xml.gz` asset (not the separate `plus` variant).
  A bounded 64 KiB compressed read confirmed WN-LMF 1.3 XML: `LexicalResource`,
  `Lexicon` (`id=oewn`, `language=en`, `version=2025`, `license`), `LexicalEntry.id`,
  `Lemma.writtenForm`/`partOfSpeech`, `Sense.id`/`synset`,
  `SenseRelation.relType`/`target`. Later synset records are validated by the downloader;
  their contents were not part of this bounded sample. This is the data format consumed by
  `wn`, downloaded directly without installing it. CC BY 4.0 plus inherited Princeton WordNet
  license; retain attribution to both teams and the upstream license notice.

Validation streams every JSONL/CSV row, and every gzipped XML element (including gzip integrity),
without materializing the full dataset. It rejects empty datasets, non-English JSONL,
incorrect CSV headers/row widths, and malformed/incomplete input.

## Build and tests

Downloading is separate from SQLite building. From `backend`:

```powershell
uv run --no-sync python -m scripts.build_lexicon
uv run --no-sync python -m scripts.build_lexicon --kaikki path\kaikki-english.jsonl --output path\lexicon.sqlite
uv run --no-sync python -m scripts.build_lexicon --words path\fixture.txt
uv run --no-sync python -m scripts.build_lexicon --ecdict path\ecdict.csv --wordfreq
```

Default input/output are the main worktree's shared `data\lexicon\raw\kaikki-english.jsonl`
and `data\lexicon\lexicon.sqlite`. `--words` is a UTF-8 list of lemmas, one per line,
normalized with `lemma_key`; blank lines are ignored. Both explicit paths avoid needing Git.
`.\scripts\dev.ps1 lexicon` orchestrates downloading and combined enrichment/packaging;
see [local setup](../../docs/dev/setup.md#lexicon-release). From `backend`, the equivalent
entrypoint is `uv run --no-sync python -m scripts.lexicon_release` with optional
`--raw-dir PATH --output PATH --dist-dir PATH --date yyyy-MM-dd`. All three path overrides
avoid Git lookup; otherwise defaults resolve through the main worktree. Relative overrides
are relative to the process working directory (`backend` via `dev.ps1`).

The release always composes ECDICT, wordfreq and OEWN, in that order. It retains verified
download records and database source metadata in the packaged manifest, includes internal
`SHA256SUMS`, and writes an archive-specific external `.sha256` sidecar. It never replaces
an existing archive/sidecar or a different existing database. A byte-identical database may
be reused for another release date. All generated stages live under ignored output paths,
not the system temporary directory; atomic exclusive publication requires hard-link support.
Release failures identify the stage and exit nonzero, with stages/new publications removed
but verified raw downloads preserved. Packaging tests use synthetic sources with a test-only
OEWN pin and deny network; production retains the official pin.

Focused offline acceptance (including real PowerShell dispatch in a synthetic main/linked
Git worktree pair) from `backend`:

```powershell
New-Item -ItemType Directory -Force .dev | Out-Null
uv run --no-sync pytest tests\unit\test_lexicon_release.py tests\unit\test_lexicon_release_command.py --basetemp=.dev\lexicon-release-tests -q
```

From the root: `pwsh -NoProfile -File .\scripts\tests\lexicon.Tests.ps1`.

The builder hashes input without retaining it and reads JSONL one entry at a time with `orjson`.
Lines larger than 16 MiB fail explicitly; SQLite has an 8 MiB page cache and disk-backed
temporary storage. Memory scales with the largest entry, not dataset size (plus an optional
fixture word set). It does not fetch audio or use the network. A sibling download manifest,
when present, must match the input filename, size and SHA-256; its complete record is retained
in `source.metadata.download`. Without a manifest, upstream attribution and an input hash are
still recorded.

Invalid JSON, non-object/non-English entries, missing word/POS/senses and invalid etymology
numbers fail with a line number. Missing etymology numbers (including null) default to 1.
Unusable individual senses (no nonblank gloss, including malformed objects) are skipped and
counted; `raw_glosses` is a fallback. A database without usable senses is rejected. Optional
forms/sounds/examples can be absent or incomplete. Blank source sense IDs use the gloss hash.
Duplicate identities keep their first row; additional distinct senses/forms/sounds are merged.
Ranks are one-based source order, not a renumbered list after skipped senses.

Output is built in a unique sibling `.part` file. Only after all imports/enrichers, SQLite
integrity/foreign-key checks and commit succeed is the closed stage atomically replaced into
place. Any ordinary failure removes the stage and leaves existing output untouched. A hard
process termination may leave a hidden stage/journal; never treat it as the final artifact.
Use read-only runtime connections; close readers before replacement on Windows.

### SQLite v1 and extension contract

`scripts.lexicon_schema` owns the DDL; `PRAGMA user_version = 1`. All IDs and foreign IDs are
TEXT. Lemma/lexeme/sense IDs are **compact JSON arrays**, not prefixed record-ID strings:
`["en","run"]`, `["en","run","verb",1]`, `["en","run","verb",1,"<sense-key>"]`.
Decode the array for shared dictionary materialization. Keys come exclusively from
`app.domain.dictionary_keys`; `scripts.lexicon_kaikki.key_text(key)` serializes them.
Normalized text is NFKC/case-folded/whitespace-collapsed. The original form spelling is retained
in `form.form`; `form_index.form` is normalized.

Columns below are NOT NULL unless marked `?`; JSON columns contain serialized arrays except
`source.metadata` and `pron.audio` (objects). Empty collections are `[]`/`{}`, not NULL.
All `source` columns reference `source.name`.

| Table | Columns / keys |
|---|---|
| `source` | `name` PK, `metadata` JSON (URL, license, attribution, checksum; optional download record) |
| `lemma` | `id` PK, `text`, `lang`, `kind` (`word`/`phrase`), `freq_zipf?` REAL, `cefr?`, `source`; UNIQUE(`lang`,`text`) |
| `lexeme` | `id` PK, `lemma_id` FK, `pos`, `etymology_no` positive INTEGER, `etymology_text?`, `source`; UNIQUE(`lemma_id`,`pos`,`etymology_no`) |
| `sense` | `id` PK, `lexeme_id` FK, `definition`, `glosses` JSON, `gloss_zh?`, `tags` JSON, `register` JSON, `domain` JSON, `examples` JSON, `rank` positive INTEGER, `common` INTEGER 0/1 DEFAULT 0, `source`, `source_id?`, `lexname?` |
| `pron` | `id` PK (SHA-256 of lexeme/accent/source sound), `lexeme_id` FK, `accent?` (`US`/`UK`), `ipa?`, `audio` JSON, `tags` JSON, `source` |
| `form` | `lexeme_id` FK, `form`, `tags` JSON, `source`; PK(`lexeme_id`,`form`,`tags`) |
| `form_index` | `form`, `lemma_id` FK; PK(`form`,`lemma_id`) |
| `zh_gloss` | `lexeme_id` FK, `gloss`, `source`, `sense_id?` FK; PK(`lexeme_id`,`gloss`,`source`) |
| `exam_tag` | `lemma_id` FK, `tag`, `source`; PK(`lemma_id`,`tag`,`source`) |
| `freq` | `lemma_id` FK, `zipf?` REAL, `bnc?` INTEGER, `coca?` INTEGER, `source`; PK(`lemma_id`,`source`) |
| `relation` | `source_sense_id` FK, `target_sense_id` FK, `type` (`synonym`/`antonym`/`hypernym`/`hyponym`), `source`; PK(all four columns) |
| `affix` | `lexeme_id` FK, `position` nonnegative INTEGER, `text`, `type` (`prefix`/`root`/`suffix`/`infix`), `source`; PK(`lexeme_id`,`position`,`source`) |

Indexes cover lemma text/language, lexeme lemma/POS/etymology, sense lexeme/rank/ID,
pron lexeme/accent, original form text, normalized form lookup and reverse lemma lookup,
Chinese-gloss sense lookup and relation target/type. Child lookup by parent is covered by
the primary keys for remaining enrichment tables.

`sense.definition` is the first gloss; `glosses` retains all gloss strings. `examples` retains
source example objects. `register` selects register labels from tags; `domain` retains topics;
`tags` retains every source tag. `gloss_zh`, `lexname`, frequency and common selection are
reserved for enrichment, not guessed by the core importer.
US/General-American and UK/Received-Pronunciation tags map to accents, with dual-tagged
sounds producing both rows and untagged/other accents retained as NULL. `pron.audio` preserves
every sound field except IPA/tags, including filenames, URL variants and available media
license/attribution. Audio-only rows are supported. The Wiktionary text license is not an
assumption about individual media licensing.
`form_index` includes lemma spellings, inflections and explicit sense `form_of` backlinks.
Backlinks may create a target lemma without lexemes if that target is absent/filtered out.

Enrichment modules should be independent files (for example `lexicon_ecdict.py`,
`lexicon_oewn.py`) with their own tests. They **do not need to modify the core importer or
schema**. Public builder interface:

```python
build(kaikki: Path, output: Path, *,
      words: collections.abc.Set[str] | None = None,
      enrichers: Iterable[Callable[[sqlite3.Connection], None]] = ()) -> BuildResult
# BuildResult.records, BuildResult.skipped_senses: int
```

Hooks run in order after the entire core import, on the same writable transaction with foreign
keys enabled, before validation/publication. Supply source paths/options with a closure or
`functools.partial`; hooks return None. Use bound SQLite parameters, do not commit/close the
connection, run `executescript`, change schema/journal mode, or publish files inside a hook.
Register attribution with `INSERT INTO source(name, metadata) VALUES (?, ?)` before inserting
source-tagged rows (including a separate `oewn:approx` source for approximate alignments).
Any exception aborts publication. ECDICT owns Chinese gloss/tag/frequency/common updates;
OEWN owns relations and `sense.lexname` (append domain tags only if preserving existing ones).
Frequency rows are per source: ECDICT ranks and wordfreq Zipf values need not share provenance.
The canonical wordfreq `freq.zipf` and `lemma.freq_zipf` should be kept in sync by that enricher.
Enrichment-specific CLI flags may be added to `build_lexicon.main` as a small integration change;
the core CLI imports an enrichment module only when its flag is requested.

### ECDICT and wordfreq enrichment

`--ecdict PATH` and `--wordfreq` independently opt in; neither is implicitly enabled.
ECDICT runs before wordfreq when both flags are present. The requested CSV must exist;
invalid CSV, malformed nonnegative BNC/COCA ranks or a mismatched sibling download manifest
abort publication. No network or silent source fallback is used. ECDICT streams CSV rows
after streaming payload validation, retaining only the current row and its matching lexemes.

Typed callable factories (both hooks return `None`; `.result` is populated after success):

```python
from scripts.lexicon_ecdict import ecdict_enricher
from scripts.lexicon_frequency import wordfreq_enricher

ecdict = ecdict_enricher(csv_path)  # EcdictEnricher
frequency = wordfreq_enricher()  # FrequencyEnricher; installed offline English "best" list
build(kaikki, output, enrichers=(ecdict, frequency))
# Fixture option: wordfreq_enricher(lookup=callable, package_version="fixture-v1")
```

`EcdictResult` counts rows, matched/unmatched lemma rows, duplicate matched rows, unmatched
glosses, ambiguous gloss alignments and inserted glosses. `FrequencyResult` counts lemmas and
zero/unknown Zipf values. Structured `ecdict_unmatched`, `ecdict_duplicate`,
`ecdict_gloss_unresolved`, `wordfreq_unmatched` and completion events expose skipped entries
with CSV row/word/reason or frequency word. Ambiguous glosses are never silently attached.

Matching uses normalized `lemma_key("en", word)` only: no fuzzy matching or inflection lookup.
Translation lines (including literal `\n`) carry POS prefixes: `n`, `v`/`vt`/`vi`,
`a`/`adj`, `ad`/`adv`, `pron`, `prep`, `conj`, `int`/`interj`, `num`, `art`, `aux`.
Slash/ampersand-separated labels are supported; unrecognized labels are unresolved.
Unlabelled text attaches only when the lemma has exactly one lexeme; labelled text needs
exactly one matching POS lexeme. Multiple etymologies are ambiguous, not guessed. The
statistical ECDICT `pos` column is not used to invent a gloss alignment. Continuation lines
retain their last prefix. Semicolons separate glosses; whitespace-trimmed identical glosses
are deduplicated. For duplicate normalized word rows, the first CSV row wins entirely,
including ranks and tags; row order is part of the checksummed source input.

Per lexeme, the first aligned gloss is stored in the top sense's `gloss_zh` and in `zh_gloss`
with that `sense_id`; other glosses remain lexeme-level (`sense_id=NULL`). Top means lowest
`rank`, then lexical sense ID. This is a conservative POS/top-sense heuristic, **not**
English–Chinese semantic equivalence. Source sense provenance remains Wiktionary.
Exam tags are deduplicated against `zk gk cet4 cet6 ky toefl ielts gre`; other labels are ignored.
`bnc` and `frq` populate ECDICT `freq.bnc`/`freq.coca`; blank/zero ranks become NULL.

wordfreq writes every English lemma's Zipf to both `freq(source='wordfreq').zipf` and
`lemma.freq_zipf`, including zero (unknown); negative/nonfinite values fail the build.
ECDICT ranks are not converted to Zipf. Each enricher recomputes `common`, so hook order
does not affect selection: per lexeme, Zipf **>=5 selects the top two**, **>=3 selects
the top one**, and lower/zero/missing frequency selects none. Additionally the sense
carrying a primary aligned ECDICT gloss is always common, even without wordfreq.
Remaining senses stay false; unaligned or ambiguous glosses never select a sense.

`source.ecdict` records MIT attribution, exact-byte SHA-256 and verified download record
when supplied. `source.wordfreq` records package version, English/`best` options, Robyn Speer
and data-contributor attribution and Apache-2.0/data CC-BY-SA-4.0 licensing/NOTICE URL.
`uv.lock` pins the package/data snapshot. Fixture lookup versions must be explicit.
No new schema or tables are introduced. Rebuilding identical inputs produces identical
logical SQLite data (not a promise of byte-identical SQLite files).

### OEWN relation hook (2.1.4)

`scripts.lexicon_oewn.oewn_enricher(path: Path) -> Callable[[sqlite3.Connection], None]`
binds a local WN-LMF XML or `.xml.gz` file. Pass it to the core builder:

```python
from scripts.lexicon_oewn import oewn_enricher

build(kaikki, output, enrichers=(oewn_enricher(oewn_path),))
```

An explicit-path production wrapper is also available from `backend`:

```powershell
uv run --no-sync python -m scripts.lexicon_oewn --kaikki path\kaikki.jsonl --oewn path\english-wordnet-2025.xml.gz --output path\lexicon.sqlite
```

The core CLI also accepts `--oewn PATH`; it runs OEWN after any requested ECDICT/wordfreq
hooks. Without the flag the core builder retains its existing behavior. Combined enrichment
and release orchestration use the same hook; there are no new dependencies.

The parser consumes `LexicalEntry/Lemma` (`writtenForm`, `partOfSpeech`), `Sense`
(`id`, `synset`), `SenseRelation` (`relType`, `target`), and `Synset`
(`id`, `lexfile`, `Definition`, `SynsetRelation`). These names and the `lexfile` lexname
attribute match the official WN-LMF 1.3 DTD (checked 2026-11-14). POS codes `n/v/a/s/r` map
to `noun/verb/adj/adj/adv`; other POS codes are skipped. Three streaming passes first identify
matching backbone entries, then align using synset definitions, then emit relations. Only
matched IDs/alignments survive between passes; complete XML trees and unrelated relation
graphs are not retained. The XML parser does not fetch the declared external DTD.

Alignment uses the maximum Jaccard score between any individual backbone gloss and synset
definition. Tokens are NFKC/case-folded Unicode alphanumeric words (underscore excluded),
minus `a an the to of and or in on at for by with be is are that which`.
At **0.30 or above**, select the highest score; ties use ascending etymology number,
sense rank and ID. Below threshold, including missing/blank definitions or empty token sets,
use the first etymology's top-ranked sense. A relation uses `oewn:approx` if either endpoint
falls back; otherwise `oewn`. Synset membership supplies bidirectional synonyms. Explicit
relations preserve direction; unsupported types (including instance/meronym/also/similar),
unmatched/missing targets, and self-edges are ignored. No placeholder senses are created.
`Synset.lexfile` fills only an empty aligned `sense.lexname`; first source-order assignment
wins collisions, and existing domain tags/lexnames remain untouched.

Both source records include OEWN/Princeton attribution, license, checksum and alignment policy.
A sibling download manifest, if present, must match the OEWN filename, size and checksum;
its original record is preserved. Plain XML fixtures without a manifest are supported.
Imports are idempotent on an unchanged backbone and use only the caller's transaction:
malformed XML, truncated gzip, non-English/empty input or manifest mismatch abort publication.
The focused fixture `tests/fixtures/oewn-small.xml` is a small synthetic WN-LMF 1.3 document,
not a full download; tests exercise both it and its gzip encoding.

Focused, network-free tests from `backend`:

```powershell
New-Item -ItemType Directory -Force .dev | Out-Null
uv run --no-sync pytest tests\unit\test_download_lexicon.py --basetemp=.dev\lexicon-tests -q
uv run --no-sync pytest tests\unit\test_build_lexicon.py --basetemp=.dev\lexicon-build-tests -q
uv run --no-sync pytest tests\unit\test_lexicon_ecdict.py --basetemp=.dev\lexicon-ecdict-tests -q
uv run --no-sync pytest tests\unit\test_lexicon_oewn.py --basetemp=.dev\lexicon-oewn-tests -q
```

From the repository root, run `.\scripts\dev.ps1 check` and
`.\scripts\dev.ps1 test -Backend` for repository validation.

### Committed runtime fixture (2.1.5)

From `backend`, rebuild the 50-lemma fixture entirely offline:

```powershell
uv run --no-sync python -m scripts.build_fixture_lexicon
uv run --no-sync python -m scripts.build_fixture_lexicon --output .dev\lexicon-small-rebuilt.sqlite
```

The default output is `tests\fixtures\lexicon_small.sqlite`. The curated word list
`lexicon-small.words`, synthetic wiktextract `lexicon-small.jsonl`, ECDICT-shaped
`lexicon-small-ecdict.csv`, WN-LMF `lexicon-small-oewn.xml` and explicit frequency snapshot
`lexicon-small-frequency.json` are committed beside it. They contain original test glosses,
not upstream extracts; source names in the database indicate the production processing route,
not claims of upstream authenticity. The wrapper delegates to `build` with the word filter and
the unmodified ECDICT, frequency and OEWN hooks; it never creates or patches SQLite rows itself.
The injected frequency version is `synthetic-fixture-v1`. Input hashes and the logical database
dump are reproducible; SQLite byte layout is not a compatibility guarantee.

The production Kaikki importer extracts English `suffix` (alias `suf`) templates of the form
`{{suffix|en|base|suffix}}` into the existing `affix` table. Positions 0/1 contain the normalized
base (`type='root'`) and hyphen-prefixed suffix (`type='suffix'`), with Wiktionary provenance.
This positional contract is documented by
[Wiktionary's suffix template](https://en.wiktionary.org/wiki/Template:suffix/documentation)
(checked 2026-11-14). Display metadata such as `alt1` does not replace the base lemma identity.
Non-English component language overrides, missing/malformed components, extra positional
components, wiki markup and conflicting supported decompositions are skipped, not guessed.
Equivalent duplicate templates collapse; duplicate backbone records retain the first pair.
Other etymology templates are not parsed. No new schema or relation type is introduced.

The fixture's `decision` source explicitly supplies base `decide`, suffix `ion` and display
stem `alt1=decis`; both affix rows now come from this production transform. Resolve a root's
`text` with `get_lemma` and `lexemes` to follow the structured base→derived association;
`affix.lexeme_id` identifies the derived lexeme. No fixture-only SQL inserts those rows.
Use `app.services.lexicon.LexiconReader` for runtime reads and the pytest `lexicon_reader`
fixture in consumers' tests. See [testing](../../docs/dev/testing.md#rebuild-and-verify-the-small-lexicon)
for the focused offline test command.
