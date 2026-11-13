---
applyTo: "frontend/**"
---

# Frontend rules

- Vue 3.5 `<script setup lang="ts">`, TypeScript 6.0 (do not upgrade to 7 — vue-tsc needs the JS API).
- UI building blocks: Naive UI components + UnoCSS utilities + Lucide icons (`<i-lucide-name />` via unplugin-icons). No other UI/icon libraries.
- Styling: design tokens only. Use UnoCSS theme classes (`p-4`, `text-sm`, `bg-surface`, `text-muted`) or `var(--pw-*)`. No hex/rgb, no arbitrary values like `p-[13px]`, no inline `style` with literals. Source of truth: `src/design/tokens.ts`; doc: `docs/ui/tokens.md`.
- Reuse domain components from `src/components/` (catalogue: `docs/ui/components.md`). Add new shared components there and to the `/dev/design` preview page.
- Structure: `src/features/<feature>/` owns its pages, composables and feature-only components. Shared code in `src/components`, `src/composables`, `src/stores`.
- API: only through `src/api/client.ts` (openapi-fetch with generated `schema.d.ts`). Never hand-write request/response types; run `./scripts/dev.ps1 gen-api`.
- State: Pinia setup stores named `useXxxStore`; composables `useXxx`.
- Text: vue-i18n keys only, add to both `src/i18n/zh-CN.json` and `src/i18n/en.json`.
- Patterns for layout, forms, feedback, empty/loading/error states: `docs/ui/patterns.md`.
- Accessibility: keyboard reachable, visible focus ring token, touch targets ≥ 44px, labels on inputs.
- Run `./scripts/dev.ps1 check` and `./scripts/dev.ps1 test -Frontend` before committing.
