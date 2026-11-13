# 0011 — Design tokens in one source

**Status:** Accepted (2026-11-13)

**Decision.**
- `frontend/src/design/tokens.ts` defines colors (light/dark), typography, spacing, radius, shadows,
  motion and layout. Brand: Google Material Blue.
- It generates CSS vars, the Naive UI theme overrides, the UnoCSS theme (the default palette is
  replaced) and the Cytoscape styles.
- UnoCSS `blocklist` and lint rules reject arbitrary values and raw color/px literals.
- Shared components are catalogued in `docs/ui/components.md` and previewed at `/dev/design`.

**Consequences.** The same look across the whole build, and changing the theme means changing one
file. A raw value requires an explicit `token-exception` comment.
