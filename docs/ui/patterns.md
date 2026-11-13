# UI patterns

## Layout & navigation

- Mobile-first. Below `lg`: header + bottom nav (Projects · Review · Words · Me). From `lg`: header
  + sidebar (Projects, All words, Review, Settings, Admin when the user is an admin).
- Each page: `PageHeader`, then content in a `max-w-content` container with `p-4 lg:p-6` and
  `gap-6` between sections.
- Detail pages on mobile open full screen. On desktop, list + detail can sit side by side
  (`lg:grid-cols-[...]` is not allowed; use named grid template classes defined in the uno config).

## Forms

- `NForm` with `rules`. Labels sit on top. The submit button goes at the end and shows `loading`
  while the request runs. Fields are disabled while submitting.
- Server errors: the API returns `{ code, message, field? }`. A `field` error is shown on that
  form item; anything else becomes a `message.error(t('errors.' + code))`.
- Destructive actions (delete project, reset override) use `ConfirmAction`. Hiding a sense is
  reversible, so it doesn't need a confirm. Instead it shows a message with **Undo**.

## Feedback

| Situation | Pattern |
|---|---|
| Success of an explicit action | `message.success`, short (≤ 2 s) |
| Recoverable error | `message.error` with the i18n text of the error code |
| Page failed to load | `ErrorState` with retry |
| Background job running | `JobStatus` inline next to the affected item, never blocking the UI |
| Long-running user action (> 300 ms) | Button `loading`, or `NSpin` over that region only |

## Loading, empty, error

- First load of a content area: `NSkeleton` shaped like the content. Never a blank page.
- Refresh with existing data: keep the data and show a small spinner in `PageHeader`.
- Empty collection: `EmptyState` with a call to action (e.g. "Add your first word").
- Every async view must handle all four states: loading, empty, error, data.

## Review session

- Full-screen focus mode. The prompt is centered and the headword uses `text-3xl` on desktop and
  `text-2xl` on mobile.
- Keyboard: 1–4 choose an option or rating · Enter submit/confirm · Space play audio · H hint · Esc exit (with confirm).
- After answering: show the correct answer, the sense, a pronunciation chip and a short context
  sentence, then `RatingBar` with the auto-rating preselected.

## Words & graph

- The project tree is the default view. Graph (dagre layout) is a toggle on the same page.
- All-words graph: start from the focused lemma or a search, at depth 1, and expand on demand.
  Never render the whole graph at once (cap about 300 nodes, then ask the user to filter).
- Colors and shapes always come from tokens (see `tokens.md`). The legend is always reachable.

## Text & i18n

- Key naming: `feature.section.item` (e.g. `projects.list.empty`). Use ICU plurals.
- Dates and numbers: dayjs with the active locale, and `Intl.NumberFormat`.
- English learning content (headwords, definitions, sentences) is never translated by i18n. Only
  the UI chrome is.

## Dark mode

- Never assume a white background. Use `bg-page`, `bg-surface` and `bg-raised`.
- Images get a 1px `border-base` so they don't bleed into dark surfaces.

## Accessibility

- Everything is reachable by keyboard, with the focus ring token visible.
- Icon-only buttons need an `aria-label` (from i18n).
- Color is never the only signal. Relation and rating badges also carry text or an icon.
