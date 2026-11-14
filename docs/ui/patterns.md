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

## Mnemonics

The selected lemma, lexeme or sense notes section labels both ordinary notes and mnemonics.
New-note kind controls keep separate drafts; editing an existing note does not change its kind.
`MnemonicSuggestion` is feature-local: its explicit action displays a separate text-only
result with Use in draft and Cancel. A nonempty draft requires `ConfirmAction` before
replacement. Acceptance remains editable and never calls the notes API; only Save persists.
Disabled/budget/provider/timeout states have localized retry feedback and never disable manual
editing. Cancellation, disposal and target/user changes invalidate pending responses and polling.
Drafts use owner-scoped tab session storage; failed requests retain text, and storage failure
falls back to memory. Auth identity/tokens remain exclusively in the auth store.

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

## Study plans and personal scheduling

The project plan page reuses the project editor and preserves the full initial plan on
replacement saves. Clearing optional exam/cap fields submits null; zero is a meaningful pause,
not an omitted value. Desired retention has its own labeled form and API call, strictly between
zero and one, and explains that only future scheduling changes.

The review entry is a dashboard/project picker, not an implicitly chosen project. Counts,
exam warnings and forecasts use server results. No answer history is distinct from 0% retention.
Each resource has loading/retry feedback; refresh removes stale snapshots. Forecast headings
explicitly label UTC dates and distinguish actual due dates from simulated review volume.
Priority controls are large labeled buttons, work without dragging, and paginate the complete
visible selection. Preparing/resetting a draft explicitly uses tree order; saving is never an
automatic side effect of reading a project.

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

- Study-plan consumers use the generated `GET /api/projects/{id}/study-plan` contract.
  Raw due/new counts, today's completed counts and the capped/paginated queue have different
  meanings; do not infer totals from the queue page length. Save settings through project PATCH
  with the full plan object. Reorder sends all effectively visible selected sense IDs to
  `PUT .../study-plan/order`; do not send hidden items or rebuild their positions on restore.
  Display exam impossibility and seven-day-buffer risk separately. UTC forecast dates and
  stored exam instants are converted for display, never recalculated from the displayed local
  date. Dashboard retention null means no data, not 0%. Queue reads do not introduce cards;
  a framework attempt must retain the issued `memory_version` until confirmation.
- `/projects` uses responsive cards, paginated API data and shared loading/empty/error patterns.
  Refresh and failed pagination keep confirmed rows; Retry repeats the failed page. Deletion uses
  `ConfirmAction` and only removes a card after API success; deleting a page's final card returns
  to the preceding page. Words remain in the personal collection.
- `/projects/new` and `/projects/:id/edit` use full-page, top-labelled forms, including languages
  and the complete study plan. Defaults match the generated contract (`en`, `zh`, daily new 20).
  Optional review cap and exam date clear to null; dates display locally and submit as UTC.
  Edits preserve untouched plan fields because supplying `plan` replaces the full plan.
  Numeric inputs accept safe non-negative integers; server field errors remain beside inputs.
- `/projects/:id` loads project metadata and the paginated project vocabulary tree separately.
  Missing and other-owner IDs share the localized unavailable state. Raw server messages are
  never displayed. Refreshes and failed page changes retain the last confirmed tree; Retry
  repeats the failed page. Add and settled enrichment jobs refresh the tree, not metadata.
- The tree reads `include_hidden=true` so hidden nodes remain recoverable. The default view
  excludes effectively hidden nodes; **Manage hidden items** exposes directly hidden and
  ancestor-hidden nodes separately. Hide/restore changes only the chosen membership flag, and
  Undo reverses the last successful visibility change, even after changing pages. Restoring a
  descendant does not restore its ancestor. Pagination counts all included lemmas, so a page
  may contain no visible words. Each lemma links to `/words/:lemmaId`.
- Tree browser selectors: `project-tree`, `project-tree-show-hidden`, `project-tree-visibility`,
  `project-tree-undo`, `project-tree-action-error`, `project-tree-word-link`,
  `project-tree-previous`, and `project-tree-next` (`data-testid`). Actions have
  `data-tree-table` and `data-tree-id` on their container and localized accessible names.
- The project header opens a token-sized, scrollable add-word modal that fits mobile viewports.
  Input searches authenticated `POST /api/dictionary/candidates`; choose a candidate and explicit
  senses through `SenseSelectList` (common senses initially selected). With no common senses,
  selection is required. Editing input invalidates old candidates; empty/error results permit
  another search. Only the search/submit region is busy, and the modal can always be closed.
  `POST /api/projects/{id}/dictionary` sends original structured lemma/sense keys, not display IDs.
  Success retains selections for safe repeat adds, deduplicates job IDs and preserves terminal
  statuses. Inline `JobStatus` polls owner-visible `GET /api/jobs/{id}`; polling failures have Retry,
  whereas failed jobs remain terminal without undoing an add. Closing aborts requests/polling;
  reopening retains results and job statuses and resumes only pending jobs. Unmounting cancels
  requests/timers. An interrupted add may already have committed; repeating it is safe.
  Tree integration listens to `added` and `jobsSettled` rather than refetching project metadata.
- Add-flow browser selectors: `project-add-word`, `add-word-dialog`, `add-word-input`,
  `add-word-search`, `add-word-candidate`, `add-word-submit`, `add-word-error`,
  `add-word-success`, `add-word-close`, `job-status`, `job-retry` (`data-testid`).
  Senses are checkbox roles labelled by their English definitions; job rows expose
  `data-job-id` and `data-job-status`.
- Browser test contracts: `projects-page`, `project-list`, `project-card`, `project-create`,
  `project-edit`, `project-delete`, `project-editor`, `project-form`, `project-save` and
  `project-detail` are `data-testid` selectors. Inputs use `project-name`,
  `project-description`, `project-target_lang`, `project-source_lang`, `project-daily-new`,
  `project-review-cap` IDs; `#project-exam-date input` targets the implicitly labelled date input.
  Route IDs are opaque record IDs passed via
  named routes, not manually split or concatenated.

## Lemma detail

- `/words/:lemmaId` (named route `word`, opaque `lemmaId` parameter) shows effective dictionary
  data with shared word, POS, pronunciation and sense components. It shows all visible cached
  senses, independent of any project's membership or hidden-state selection.
- Personal field editors support lemma headword/CEFR, lexeme etymology and sense definition/
  Chinese gloss. PATCH preserves other fields and gloss languages. Reset uses `ConfirmAction`
  and removes the item's **entire** own override, not just the fields shown in the editor.
  Shared dictionary rows are never edited. Saved changes are re-read from the effective endpoint.
- The target selector and sense Note action manage own lemma/lexeme/sense notes. Add and edit
  preserve failed drafts; delete requires confirmation. Refresh retains confirmed content and
  unsaved text. Drafts remain in Pinia memory across project navigation (reopen the same editor);
  changing the signed-in user clears them. Drafts do not enter browser storage; browser reload
  restores only saved server data.
- Pronunciation pointers are opaque media IDs, not public URLs. Fetch with the authenticated API
  client (`parseAs: 'blob'`), then play a temporary object URL through the shared player. Empty
  blobs, missing audio, transport/API and playback errors are explicit; navigation/unmount aborts
  pending fetches, stops playback and revokes object URLs. The pronunciation button toggles
  playback or cancels an in-flight request, and exposes its state to assistive technology.
- Browser selectors: `word-detail`, `word-refresh`, `word-lemma-edit`, `word-lemma-reset`,
  `word-lexeme` (`data-lexeme-id`), `word-lexeme-edit`, `word-lexeme-reset`, `word-sense`
  (`data-sense-id`), `word-sense-edit`, `word-sense-reset`, `word-sense-note`,
  `word-override-editor`, `word-override-save`, `word-notes` (`data-target-id`),
  `word-note` (`data-note-id`), `word-note-editor`, `word-note-edit`, `word-note-delete`,
  `word-pronunciation` (`data-media-id`) and `word-missing-audio`.
  Override inputs have `word-override-text`, `word-override-cefr`,
  `word-override-etymology_text`, `word-override-definition`, `word-override-gloss` IDs.
  The note editor's `textarea` is scoped beneath `word-note-editor`. Project tree links should
  use `{ name: 'word', params: { lemmaId: opaqueLemmaId } }`, without splitting record IDs.

## Review session

- `/projects/:id/review` renders the server queue in a responsive focus region within the existing
  app shell. Loading, initial-empty/completed, no-usable, unavailable, stale/expired and retryable
  failures are distinct. A no-usable card is never silently skipped; only stale/expired/unavailable
  attempts offer an explicit queue reload. Unavailable hints leave answer/give-up enabled.
- Answer/give-up bodies and selected confirmation ratings are saved before sending. Failed requests
  lock editing until retry/recovery, keeping the original answer/duration/rating. Feedback never
  advances the queue: only the server's durable confirmed receipt does. Progress is then re-read.
  Active attempts resume from owner/project-scoped tab storage; leaving via navigation requires a
  dialog and tab reload warns while an attempt is active. Browser storage failures block submission.
- Browser selectors: `review-session`, `review-loading`, `review-exercise` (`data-attempt-id`,
  `data-status`), `review-error` (`data-error`), `review-retry`, `review-restart`, `review-empty`,
  `review-audio-error`, `review-exit` are `data-testid` values. Choice/rating groups retain localized
  accessible names and scoped keyboard shortcuts; ratings also expose `data-rating`. Submit,
  hint, give-up and confirm use localized button names; typed answers use a labelled `input`.
  Protected audio is explicitly unavailable on failure; retry playback, give-up and exit remain
  available without revealing spelling.

- Full-screen focus mode. The prompt is centered and the headword uses `text-3xl` on desktop and
  `text-2xl` on mobile.
- Keyboard: in the focused choice/rating group, 1–4 select and Enter submits/confirms;
  Space confirms in ratings, activates focused buttons normally, or requests audio on the
  focused exercise frame. H requests a hint outside editable fields; Esc outside editable
  fields requests exit (the page confirms). Typed inputs retain normal H/Space/digit entry
  and ignore IME-composition Enter. Handled shortcuts stop propagation; there are no global
  key listeners. After grading choices are disabled and focus moves to the suggested rating.
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
