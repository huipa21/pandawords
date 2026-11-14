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

Downloading is separate from SQLite building. Task 2.1.2 implements the builder;
`.\scripts\dev.ps1 lexicon` is not implemented yet and is not a download command.
The intended pipeline is download → offline build → `data\lexicon\lexicon.sqlite`.

Focused, network-free tests from `backend`:

```powershell
New-Item -ItemType Directory -Force .dev | Out-Null
uv run --no-sync pytest tests\unit\test_download_lexicon.py --basetemp=.dev\lexicon-tests -q
```

From the repository root, run `.\scripts\dev.ps1 check` and
`.\scripts\dev.ps1 test -Backend` for repository validation.
