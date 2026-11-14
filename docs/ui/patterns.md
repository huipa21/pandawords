# UI patterns

## Layout & navigation

- Mobile-first. Below `lg`: header + bottom nav (Projects · Review · Words · Me). From `lg`: header
  + sidebar (Projects, All words, Review, Settings, Admin when the user is an admin).
- Each page: `PageHeader`, then content in a `max-w-content` container with `p-4 lg:p-6` and
  `gap-6` between sections.
- Detail pages on mobile open full screen. On desktop, list + detail can sit side by side
  (`lg:grid-cols-[...]` is not allowed; use named grid template classes defined in the uno config).
- `src/app/router.ts` separates `/login` (auth layout) from the app layout. Documented routes
  have localized placeholders until their feature tasks land; `/review` is the global review
  entry. `/dev/design` is registered only in development and requires authentication.
  Admin links are visible only to admins; both admin routes have role guards.
  All app routes require authentication. Users with temporary passwords are redirected to
  `/change-password` until a successful change issues fresh credentials.
- The root provides Naive config, message, dialog and notification contexts to both layouts.
  Bottom navigation reserves token-based space plus the device safe area.

## Forms

- `NForm` with `rules`. Labels sit on top. The submit button goes at the end and shows `loading`
  while the request runs. Fields are disabled while submitting.
- Server errors: the API returns `{ code, message, field? }`. A `field` error is shown on that
  form item; anything else becomes a `message.error(t('errors.' + code))`.
- Login and password change use generated API payloads, localized required-field rules,
  and disabled/loading submit controls. Unknown error codes use a localized fallback, never
  raw server text. Transport failures are visible messages.
- Access tokens and user identity live only in the Pinia auth store. Refresh credentials are
  httpOnly cookies, sent with `credentials: include`; no auth state enters browser storage.
  Navigation waits for one initial refresh. A forced-change refresh returns
  `403 auth.password_change_required` and clears the cookie: return to login with a localized
  message; logging in supplies the token needed for password change.
- Protected API 401s share one refresh and retry once. Login, refresh, password change and logout
  never trigger recovery. Recovery resets local state rather than recursively calling logout.
  Cookie-changing operations wait for in-flight refresh, and session versions prevent stale
  results from restoring tokens after logout or a newer login.
- Explicit logout with an expired bearer uses the independent auth transport to refresh once
  and retry revocation with the rotated access token, without restoring visible auth.
  Refresh 401/403 clears the cookie server-side and completes local logout; transport/server
  failures remain visible errors. Queued logins wait until this cookie cleanup finishes.
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
- The Pinia preferences store persists theme (`system` / `light` / `dark`) and locale
  (`zh-CN` default / `en`) in `pandawords.preferences`. System mode follows live
  `prefers-color-scheme` changes; explicit themes ignore them. The same resolved theme drives
  Naive overrides and the document `data-theme`. Storage failures retain in-memory preferences.

## Accessibility

- Everything is reachable by keyboard, with the focus ring token visible.
- Icon-only buttons need an `aria-label` (from i18n).
- Color is never the only signal. Relation and rating badges also carry text or an icon.
