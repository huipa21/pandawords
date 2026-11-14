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

## Build (offline, `dev.ps1 lexicon`)

```
download → data/lexicon/raw/   (kaikki .jsonl, ecdict.csv, OEWN .xml.gz; manifest.json)
build    → data/lexicon/lexicon.sqlite   (read-only at runtime)
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
from `backend`; `dev.ps1 lexicon` orchestration remains task 2.1.6.

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
  POS level (`sense.gloss.zh` for the top sense, `lexeme`-level gloss list otherwise). OEWN
  relations attach by best gloss overlap (a token Jaccard score; below the threshold they attach to
  the lexeme's top sense with `source='oewn:approx'`).
- Test fixture: `backend/tests/fixtures/lexicon_small.sqlite`, about 50 words covering polysemy,
  phrases, US/UK differences and derivations. It is built by the same script with `--words fixture.txt`.

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
