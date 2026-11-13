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
file. A raw value requires an explicit `token-exception` comment with a reason immediately before
the affected declaration, at-rule or bound style value; it never exempts a utility class.

UnoCSS's blocklist alone only suppresses CSS, so the flat ESLint configuration enables
`unocss/blocklist` as an error and checks bound class literals separately. The CSS generator and
the selected self-hosted font subsets are bundled at build time; motion durations also respect
`prefers-reduced-motion`. Computed style values supplied from elsewhere must still use tokens,
since a static lint rule cannot prove their runtime values.
