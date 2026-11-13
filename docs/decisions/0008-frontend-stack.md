# 0008 — Frontend stack

**Status:** Accepted (2026-11-13)

**Decision.** Node 24 LTS, pnpm, Vue 3.5, Vite 8, **TypeScript 6.0.x**, vue-tsc 3.x, Vue Router 5,
Pinia 4, Naive UI 2.45, UnoCSS (theme driven by tokens), Lucide icons via unplugin-icons, Cytoscape.js
(fcose, dagre), vue-i18n 11 (zh-CN, en), @vueuse/core, openapi-typescript + openapi-fetch,
vite-plugin-pwa, vitest, Playwright, @antfu/eslint-config.

**Why TS 6.0, not 7.0.** TypeScript 7 is the native (Go) compiler. As far as we know it doesn't
provide the JS language-service API that vue-tsc and Volar rely on. Revisit when vue-tsc supports 7.

**Consequences.** There is one UI library and one icon set. Visual consistency is enforced through
tokens (ADR 0011). The root is a private pnpm workspace; the frontend package owns its scripts and
dependencies, and pins TypeScript to an exact 6.0.x version. Both package manifests declare the same
pnpm `packageManager` version. The hello page uses vue-i18n messages in `zh-CN` (the default) and
`en` (the fallback); locale selection is part of the later app shell.
