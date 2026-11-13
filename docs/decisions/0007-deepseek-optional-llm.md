# 0007 — DeepSeek as the only, optional LLM

**Status:** Accepted (2026-11-13)

**Context.** LLM features (scenario exercises, linking passage words to senses, mnemonics, morpheme
fallback) are valuable, but the app must work without them. DeepSeek is widely used in China and is
OpenAI-compatible.

**Decision.** A single provider, DeepSeek, through the `openai` SDK with `base_url`. All calls go
through `services/llm.py`. Results are cached on shared records where they aren't user-specific.
There's a per-user daily budget. When the key is missing or the call fails, the feature falls back
or is skipped.

**Consequences.** Low token cost (caching plus a stable prompt prefix). Adding another provider
later would be a new ADR.
