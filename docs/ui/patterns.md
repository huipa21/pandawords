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
- Admin users uses NDataTable from `lg` and a card list below it. Pagination retains the
  confirmed page on failure; retry repeats the failed request. Existing rows remain visible.
  Create and password reset show a transient, copyable temporary password, cleared on dismissal
  or page disposal (never stored or logged). Clipboard failures offer localized manual-copy
  guidance. Disable, password reset and role changes require `ConfirmAction`; enable is immediate.
  Self-disable/demotion are unavailable. Since the signed-in administrator is enabled, any other
  administrator is not the last enabled one; concurrent last-admin conflicts are enforced by the
  backend and surfaced in both locales. New shared page-state/dialog components are previewed
  in `/dev/design`.

## Projects

- `/projects` uses responsive cards, paginated API data and shared loading/empty/error patterns.
  Refresh and failed pagination keep confirmed rows; Retry repeats the failed page. Deletion uses
  `ConfirmAction` and only removes a card after API success; deleting a page's final card returns
  to the preceding page. Words remain in the personal collection.
- `/projects/new` and `/projects/:id/edit` use full-page, top-labelled forms, including languages
  and the complete study plan. Defaults match the generated contract (`en`, `zh`, daily new 20).
  Optional review cap and exam date clear to null; dates display locally and submit as UTC.
  Edits preserve untouched plan fields because supplying `plan` replaces the full plan.
  Numeric inputs accept safe non-negative integers; server field errors remain beside inputs.
- `/projects/:id` loads project metadata and reserves the tree area for task 2.6.4. It does not
  fetch or infer tree membership. Missing and other-owner IDs share the localized unavailable
  state. Raw server messages are never displayed.
- Browser test contracts: `projects-page`, `project-list`, `project-card`, `project-create`,
  `project-edit`, `project-delete`, `project-editor`, `project-form`, `project-save` and
  `project-detail` are `data-testid` selectors. Inputs use `project-name`,
  `project-description`, `project-target_lang`, `project-source_lang`, `project-daily-new`,
  `project-review-cap` IDs; `#project-exam-date input` targets the implicitly labelled date input.
  Route IDs are opaque record IDs passed via
  named routes, not manually split or concatenated.

## Review session

- Full-screen focus mode. The prompt is centered and the headword uses `text-3xl` on desktop and
  `text-2xl` on mobile.
- Keyboard: 1–4 choose an option or rating · Enter submit/confirm · Space play audio · H hint · Esc exit (with confirm).
- After answering: show the correct answer, the sense, a pronunciation chip and a short context
  sentence, then `RatingBar` with the auto-rating preselected.

## Words & graph

- Shared word components are presentation-only. Pages map generated API data into
  `components/word/types.ts` and own fetching, persistence, permission checks and Undo feedback.
  Supply effective sense content plus hidden/customized markers; do not resolve overrides twice.
- Sense selection defaults only when the model is undefined; pass `[]` to explicitly clear it.
  Mount with loaded candidates or leave the model undefined until candidates arrive. Controlled
  selections survive candidate changes; page adapters reconcile removals and project changes.
- Audio accepts a browser-playable source or emits an event-only request. Do not pass protected
  URLs requiring bearer headers directly to native audio; later pages resolve authorized media.
  Shared playback permits one sound at a time, with localized failure feedback. All controls
  retain ≥44px touch targets, including visual small audio buttons and tree expanders.
- Note editors emit controlled draft and save/cancel events, never write directly to the API.
  Mark saving/disabled during persistence and present page-level feedback.

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
