# Lexicon pipeline & enrichment

## Sources

| Source | Gives us | License / note |
|---|---|---|
| Wiktionary via kaikki.org (wiktextract English JSONL) | lemma → etymology/POS → senses, glosses, examples, IPA (US/UK tags), audio URLs, forms/inflections, derived/related terms, synonyms/antonyms, etymology templates (affixes) | CC BY-SA. Keep attribution on sense/media `source` and in exports |
| Open English WordNet (`wn` package, latest `oewn`) | synonym/antonym/hypernym/hyponym relations, lexnames (concept tags) | CC BY 4.0 |
| ECDICT (skywind3000/ECDICT csv) | Chinese glosses, exam tags (`zk gk cet4 cet6 ky toefl ielts gre`), Collins/Oxford flags, BNC/COCA frequency, inflections (`exchange`) | MIT |
| wordfreq | Zipf frequency (used to pre-check "common" senses and band words) | Apache-2.0 / data CC BY-SA |
| spaCy `en_core_web_sm` | lemmatizing user input, sentences and passages | MIT |
| lemminflect | inflection fallback when Wiktionary forms are missing | MIT |

Field names in kaikki and ECDICT must be checked against the real files in task 2.1.x. Record them in
`backend/scripts/README.md`.

## Build (offline, `dev.ps1 lexicon`)

```
download → data/lexicon/raw/   (kaikki .jsonl, ecdict.csv, oewn via wn data dir; versions in manifest.json)
build    → data/lexicon/lexicon.sqlite   (read-only at runtime)
```

- `lexicon.sqlite` tables: `lemma`, `lexeme`, `sense`, `pron`, `form`, `relation`, `zh_gloss`,
  `exam_tag`, `freq`, `affix`, plus `form_index(form → lemma)` for inflection lookup.
- The build streams the input (orjson, line by line) so it stays within the server's 4 GB RAM. It
  normally runs on the laptop. The artifact is transferred to the server as
  `pandawords-lexicon-<date>.tar.gz` and mounted read-only.
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
