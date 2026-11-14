# Design tokens

Graph rendering uses `graphNodes` shapes, `graphEdges` line/color aliases and light/dark
`themes` only. `graphMetrics` owns canvas height, control width, node/focus dimensions,
border/edge widths and label size/width. Cytoscape styles rebuild on resolved theme changes;
the design preview can explicitly supply either theme. Semantic edges always show their
directed target arrow, even when reciprocal links are present.

**Source of truth:** `frontend/src/design/tokens.ts`. Everything else is generated from it:

| Output | Used by |
|---|---|
| CSS custom properties `--pw-*` on `:root` / `[data-theme='dark']` | Scoped CSS, UnoCSS theme |
| `naive-theme.ts` → `themeOverrides` / `darkThemeOverrides` (hex values, because Naive UI computes derived shades) | Naive UI components |
| `uno.config.ts` theme (replaces the default palette, font sizes, radius and shadows) | Utility classes |
| `cytoscape-style.ts` (reads the computed CSS vars, rebuilt on theme change) | GraphCanvas |

**Enforcement:**
- UnoCSS's `blocklist` omits forbidden CSS; the enabled `unocss/blocklist` ESLint rule makes
  literal classes such as `p-[13px]` and `bg-red-500` fail lint. A companion rule checks literals
  in bound `:class` and `v-bind` expressions. Unspecified spacing steps, literal lengths, and
  non-token font sizes, radii, shadows and motion durations are also blocked.
- ESLint rejects hex/rgb/px literals and non-token font sizes in `.vue` `<style>` declarations and
  at-rules, static `style` attributes, and literal values in bound styles. Numeric dimensions in
  bound style objects are rejected too, because Vue converts them to pixels. Values computed
  elsewhere cannot be checked statically and must still come from tokens.
- A nonempty `/* token-exception: reason */` comment immediately before a single declaration or
  at-rule permits raw literals in that declaration or at-rule only. For a bound style object, put
  the comment immediately before its value. Exceptions do not exempt UnoCSS classes:

  ```vue
  <template>
    <div style="/* token-exception: external diagram geometry */ width: 13px" />
    <div :style="{ width: /* token-exception: external chart API */ '13px' }" />
  </template>

  <style scoped>
  .external-diagram {
    /* token-exception: external diagram geometry */
    width: 13px;
  }
  </style>
  ```

The generated CSS includes `--pw-*` variables for both themes, layout, typography and motion.
The spacing variable for `0.5` is `--pw-space-0-5`. Use `pw-focus-ring` for the tokenized outline
and offset; for keyboard focus use `focus-visible:pw-focus-ring`. Reduced-motion media rules set all
three duration variables to zero and suppress CSS animation/transition durations and delays,
including those from UI components. `createCytoscapeStyle(element)` reads computed variables;
rebuild the styles after changing the theme.

Brand: **Google Material Blue**. Neutrals follow the Material grey scale. Dark mode follows the
system by default, with a toggle (system / light / dark) stored in preferences.

## Color — semantic

| Token (`--pw-color-*`) | Uno class | Light | Dark |
|---|---|---|---|
| `primary` | `bg-primary` `text-primary` | `#1976D2` | `#64B5F6` |
| `primary-hover` | `bg-primary-hover` | `#1E88E5` | `#90CAF9` |
| `primary-pressed` | `bg-primary-pressed` | `#1565C0` | `#42A5F5` |
| `primary-soft` (tinted bg) | `bg-primary-soft` | `#E3F2FD` | `#0D2A4A` |
| `on-primary` | `text-on-primary` | `#FFFFFF` | `#0D1B2A` |
| `info` / `info-soft` | `text-info` `bg-info-soft` | `#0288D1` / `#E1F5FE` | `#29B6F6` / `#062E3F` |
| `success` / `success-soft` | | `#2E7D32` / `#E8F5E9` | `#66BB6A` / `#0F2E12` |
| `warning` / `warning-soft` | | `#ED6C02` / `#FFF3E0` | `#FFA726` / `#3A2406` |
| `error` / `error-soft` | | `#D32F2F` / `#FFEBEE` | `#EF5350` / `#3B1012` |
| `text` | `text-fg` | `#212121` | `#E3E3E3` |
| `text-muted` | `text-muted` | `#616161` | `#A8A8A8` |
| `text-disabled` | `text-disabled` | `#9E9E9E` | `#6B6B6B` |
| `border` | `border-base` | `#E0E0E0` | `#3A3A3A` |
| `divider` | `border-divider` | `#EEEEEE` | `#2A2A2A` |
| `bg` (page) | `bg-page` | `#FFFFFF` | `#121212` |
| `surface` (panels, sidebar) | `bg-surface` | `#FAFAFA` | `#1A1A1A` |
| `surface-raised` (cards, popovers) | `bg-raised` | `#FFFFFF` | `#232323` |
| `focus` | ring | = `primary` | = `primary` |

Warning orange is below 4.5:1 contrast on white. Use it for fills and icons only. For warning text,
put `text` on `warning-soft`.

## Color — graph nodes (`--pw-node-*`, Uno `text-node-*` / `bg-node-*`)

| Node | Light | Dark | Cytoscape shape |
|---|---|---|---|
| `lemma` | `#37474F` | `#B0BEC5` | round-rectangle (large) |
| `lexeme` | `#5E35B1` | `#B39DDB` | round-rectangle |
| `sense` | `#3949AB` | `#9FA8DA` | ellipse |
| `phrase` | `#C2185B` | `#F48FB1` | round-hexagon |
| `morpheme` | `#EF6C00` | `#FFB74D` | diamond |
| `sentence` | `#00796B` | `#4DB6AC` | rectangle |
| `passage` | `#558B2F` | `#AED581` | barrel |
| `tag` | `#757575` | `#BDBDBD` | tag |

## Color — graph edges (`--pw-edge-*`)

| Edge | Color | Line |
|---|---|---|
| `synonym` | success | solid |
| `antonym` | error | solid |
| `hypernym` / `hyponym` | node-sense | solid, arrow |
| `confusable` | warning | dashed |
| `derives_to` | node-lexeme | dashed, arrow |
| `composed_of` | node-morpheme | dotted |
| `contains` | node-phrase | solid |
| `used_in` | node-sentence | thin |
| `member_of` | node-tag | thin |
| `default` | text-muted | thin |

## Color — review ratings (`--pw-rating-*`)

`again` = error · `hard` = warning · `good` = success · `easy` = info

## Typography

| Token | Value |
|---|---|
| `font-sans` | `"Roboto", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif` |
| `font-serif` (headwords) | `"Roboto Serif", Georgia, serif` |
| `font-ipa` | `"Noto Sans", "Roboto", sans-serif` (IPA glyph coverage) |
| `font-mono` | `"Roboto Mono", ui-monospace, monospace` |

Latin fonts are self-hosted via `@fontsource-variable/*` (latin and latin-ext subsets). CJK text
uses system fonts, which avoids multi-MB downloads. The build selects only those two subsets and
aliases Fontsource's `* Variable` family names to the documented names above. It also includes each
font's OFL license in the build output.

| Size token | Uno | rem / px | Use |
|---|---|---|---|
| `xs` | `text-xs` | 0.75 / 12 | captions, badges |
| `sm` | `text-sm` | 0.875 / 14 | secondary text, dense tables |
| `base` | `text-base` | 1 / 16 | body |
| `lg` | `text-lg` | 1.25 / 20 | section titles, IPA |
| `xl` | `text-xl` | 1.5 / 24 | page titles |
| `2xl` | `text-2xl` | 2 / 32 | headword (detail) |
| `3xl` | `text-3xl` | 2.5 / 40 | headword (review prompt) |

Weights: 400 regular · 500 medium · 600 semibold · 700 bold. Line height: `tight` 1.25 (headings),
`normal` 1.5 (body), `relaxed` 1.75 (reading view).

## Spacing (Uno numeric scale, 1 = 4px)

Allowed steps: `0 · 0.5 (2px) · 1 (4) · 2 (8) · 3 (12) · 4 (16) · 6 (24) · 8 (32) · 12 (48) · 16 (64)`.
Other steps are blocklisted. Page padding: `p-4` on mobile, `p-6` from `lg`. Gap between stacked
sections: `gap-6`; inside cards: `gap-3`.

## Shape, elevation, motion

| Token | Value | Use |
|---|---|---|
| `radius-sm` | 4px | inputs inside tables, small badges |
| `radius-md` | 8px | buttons, inputs (Naive `borderRadius`) |
| `radius-lg` | 12px | cards, modals, drawers |
| `radius-full` | 9999px | chips, tags, avatars, pronunciation chip |
| `shadow-1` | `0 1px 2px rgb(0 0 0 / .08), 0 1px 3px rgb(0 0 0 / .06)` | raised cards |
| `shadow-2` | `0 4px 12px rgb(0 0 0 / .12), 0 2px 4px rgb(0 0 0 / .08)` | popovers, modals |
| `duration-fast` / `normal` / `slow` | 150 / 250 / 400 ms | hover / panels / graph & page |
| `ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | default |
| `ease-decelerate` | `cubic-bezier(0.05, 0.7, 0.1, 1)` | enter |

Dark mode: shadow alpha ×3. Raised surfaces are lighter (`surface-raised`). `prefers-reduced-motion`
sets the durations to 0.

## Layout & sizing

| Token | Value |
|---|---|
| Breakpoints | `sm` 640 · `md` 768 · `lg` 1024 · `xl` 1280 (mobile-first) |
| Header height | 56px |
| Sidebar width | 240px (collapsed 64px), shown from `lg` |
| Bottom nav | 56px + `env(safe-area-inset-bottom)`, below `lg` |
| Content max width | 1200px · reading view 720px |
| Control heights | small 28 · medium 36 · large 44 (Naive `heightSmall/Medium/Large`) |
| Icon sizes | 16 (dense) · 20 (default) · 24 (nav, prompts) |
| Touch target | ≥ 44px. Use `size="large"` for primary actions on mobile |
| Focus ring | 2px solid `focus`, 2px offset |
