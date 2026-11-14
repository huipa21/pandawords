# Component catalogue

Use these. If something is missing, add it here **and** to `src/components/`, with an entry on the
`/dev/design` preview page. Feature-only components stay in `src/features/<x>/components/`.

The development-only `/dev/design` route compares light/dark semantic, graph and rating tokens,
typography, spacing, radii and shadows. It includes an interactive Naive UI playground and all
currently implemented app components (the surrounding AppShell plus AppHeader, AppNavigation,
ThemeToggle and LocaleSwitch). Other catalogue entries below are planned, not preview stubs.
Preview code and its local bilingual messages are lazy-loaded behind `import.meta.env.DEV`;
neither is included in production bundles.

## Base layer: Naive UI (used directly)

| Need | Component | Rules |
|---|---|---|
| Actions | `NButton` | One `type="primary"` per view. Low emphasis: `tertiary`/`quaternary`. Destructive: `type="error"` + confirm dialog |
| Forms | `NForm`, `NFormItem`, `NInput`, `NSelect`, `NCheckbox`, `NRadioGroup`, `NSwitch`, `NDatePicker`, `NInputNumber`, `NUpload` | Labels on top. Validation rules in the form; server errors mapped to fields |
| Containers | `NCard`, `NModal` (`preset="card"`), `NDrawer` (mobile sheets), `NTabs`, `NCollapse` | Use NDrawer instead of NModal for long content below `lg` |
| Data | `NDataTable` (desktop), card list (mobile), `NTree`, `NPagination` | |
| Display | `NTag`, `NBadge`, `NTooltip`, `NPopover`, `NProgress`, `NStatistic`, `NAvatar` | |
| Feedback | `useMessage`, `useDialog`, `useNotification` (providers in AppShell), `NEmpty`, `NSkeleton`, `NSpin`, `NResult` | See patterns.md |

Icons come from Lucide only: `<i-lucide-volume-2 />` (unplugin-icons). The size follows the font
size (`text-base` = 16, `text-lg` = 20, `text-xl` = 24).

## App components (`src/components/app/`)

| Component | Purpose / key props |
|---|---|
| `AppShell` | Implemented: header, sidebar (≥ `lg`) / bottom nav (< `lg`), router outlet; root `app/App.vue` owns Naive providers and theme sync |
| `AppHeader` | Shared brand link and preference controls; authenticated password-change link and logout action |
| `AppNavigation` | Localized router links with active/keyboard states; admin-only links; `mobile?` selects bottom navigation |
| `PageHeader` | Implemented: `title`, `subtitle?`; wrapping `actions` slot |
| `EmptyState` | Implemented: NEmpty with `titleKey`, `descKey?`; `action` slot |
| `ErrorState` | Implemented: NResult with localized retry; `error` (localized text), `loading?`, `@retry` |
| `ConfirmAction` | Implemented: controlled destructive dialog; `show`, `titleKey`, `contentKey`, `params?`, `loading?`, `@confirm`, `@cancel`. Parent closes after success; loading blocks dismissal |
| `ThemeToggle` | Implemented: accessible icon button cycles system → light → dark; persists via preferences store |
| `LocaleSwitch` | Implemented: accessible icon button toggles zh-CN / en, including Naive locale and document language |
| `JobStatus` | Implemented: inline owner-job progress; generated `jobs: JobRead[]`, `active?` (default true), `update:jobs`, `settled`. Polls only queued/running rows; done/failed are terminal. Query failures preserve the last status and offer Retry. Disabling/unmounting aborts requests and timers. Preview includes every status without polling |
| `SourceAttribution` | License attribution line for dictionary content |

Project-only `AddWordDialog` lives in `src/features/projects/`. Props: `projectId`, `show`;
events: `update:show`, `added(AddToProjectRead)` and `jobsSettled(JobRead[])`
(`@jobs-settled` in templates). The tree page can refresh membership on `added` and enriched
content on `jobsSettled`; failed jobs remain terminal and do not invalidate successful adds.
Its adapter maps generated nested candidates into `WordHeader` / `SenseSelectList` presentation
models while preserving structured keys for submission.

## Word components (`src/components/word/`)

| Component | Purpose / key props |
|---|---|
| `WordHeader` | Headword in `font-serif`, kind (word/phrase), frequency band, `ExamTagBadge`s. `lemma`, `size: 'md'\|'lg'\|'xl'` |
| `PronunciationChip` | IPA in `font-ipa` + accent label (US/UK) + play. `ipa`, `accent`, `audioUrl?`. Pill shape |
| `AudioButton` | Plays through one shared audio element (only one sound at a time). `src`, `size` |
| `PosBadge` | Part of speech (localized). `pos` |
| `NodeTypeBadge` | Colored by `--pw-node-*`. `type` |
| `RelationBadge` | Colored by `--pw-edge-*`. `type` |
| `ExamTagBadge` | `tag` (ielts, toefl, cet4…) |
| `SenseItem` | Definition, zh gloss, register/domain tags, examples (collapsed), override marker, actions (edit, hide, note). `sense` (effective view), `selectable?`, `hidden?`, `editable?` |
| `SenseSelectList` | Checklist of candidate senses, grouped by lexeme, with common ones pre-checked. `v-model:selected`, `candidates` |
| `LexemeBlock` | POS + pronunciation chips + its SenseItems |
| `LemmaTree` | Presentational NTree of `items: LemmaBranch[]`; controlled `expandedKeys` / `selectedKeys` and update events, optional `defaultExpandAll`, and an `actions` slot with `table` and `id` for page-owned controls. Word headers, lexeme labels and effective senses; no project fetching |
| `NoteEditor` | Controlled `modelValue` text, `target`, `kind: note \| mnemonic`, `saving`, `disabled`; emits model update, `save({target, kind, text})`, `cancel`. Persistence belongs to pages |

Implemented word components live in `src/components/word/`. `types.ts` defines presentation
models only: `LemmaView`, `LexemeView`, `SenseView`, `Pronunciation`, `LemmaBranch` and badge
unions. Feature pages map generated API schemas to these models (no duplicate API schemas).
`WordHeader` accepts a lemma's `text`, `kind`, optional frequency label and exam tags.
`LexemeBlock` composes POS, pronunciations and senses and forwards edit/hide/note/play events.
`SenseItem` consumes the **effective** definition/gloss supplied by its caller; `overridden`
is a marker, not a local override resolver. `hidden` may explicitly override `sense.hidden`.
With `editable`, actions emit `edit(id)`, `hide(id, hidden)`, `note(id)` without API calls.
Examples are collapsed initially. Badge text is localized; graph colors use node/edge tokens.

`SenseSelectList` takes lexeme-grouped `candidates` and `v-model:selected` sense IDs.
An **undefined** selection initializes from common, non-hidden senses (and emits the defaults);
an explicit `[]` means select none. Hidden senses remain visible but disabled. A controlled
selection is never replaced when candidates change; callers reconcile stale IDs.

`AudioButton` accepts optional `src`, `disabled` and visual `size`; touch area stays ≥44px.
It emits `play(src | undefined)` on playback requests and `error` on media failure. Provided
browser-playable URLs use one shared audio element; another play stops the preceding sound.
An omitted URL is event-only (caller may resolve audio); use `disabled` for unavailable audio.
`PronunciationChip` forwards play requests and accepts `ipa`, `accent: US | UK`, `audioUrl`.
For externally managed playback, `playbackState` controls the button's pressed state and each
click emits a play request, allowing the caller to toggle playback.
No bearer-token fetching is performed here; the lemma detail page resolves protected media IDs
through its authenticated blob adapter before using the shared player.
The design preview includes a locally generated tone, not a remote pronunciation dependency.
Both theme panels demonstrate all word components, selection, hidden/customized senses,
word/phrase trees and empty states at responsive widths.

## Graph components (`src/components/graph/`)

| Component | Purpose / key props |
|---|---|
| `GraphCanvas` | Cytoscape wrapper. `elements`, `layout: 'fcose'\|'dagre'`, `focusId?`. Emits `select`, `expand`. Styles come from `cytoscape-style.ts` (tokens) and rebuild on theme change |
| `GraphLegend` | Node and edge legend from tokens. Toggles filters |
| `GraphToolbar` | Layout switch, depth, filters (node types, relation types), fit, search |

## Exercise components (`src/components/exercise/`)

| Component | Purpose / key props |
|---|---|
| `ExerciseShell` | `attemptId`, generated `prompt`, optional server `feedback`, `autoRating`, `hint`; `hintAvailable`, `hintLoading`, `disabled`, `submitting`. Prompt/answer/feedback/progress slots; hidden monotonic timer |
| `ChoiceGrid` | Generated `choices` (2–4), `v-model` opaque answer ID, `disabled`; emits `submit`. Scoped keys 1–4 select; Enter submits |
| `TypedAnswerInput` | `v-model` original answer, `disabled`, optional generated `feedback`; emits `submit` on non-IME Enter. Wrong server feedback shows deleted input and inserted expected answer; no local normalization/grading |
| `RatingBar` | Generated `autoRating`, `disabled`, `loading`. Emits `change(rating)` and `confirm(rating)`; auto-rating preselected, user can override. Token rating colors; scoped 1–4 and Space/Enter |
| `ReviewProgress` | Required `done`, `remaining`, `newCount`, `reviewCount` display counts; labelled native progress, including empty/complete sessions |

`ExerciseShell` emits `answered(AttemptAnswer)` with `{answer, duration_ms}`,
`giveUp({duration_ms})`, `hint()` intent, `confirm(Rating)`, `exit()` and `audio()` intents.
These replace the original proposed `answered {correct, usedHint, ...}` contract: only the
server can establish correctness, hint use or auto-rating. Types are aliases of generated API
schemas. The parent maps `AttemptRead` to these props, persists hint intent through the API,
sets busy props during requests, handles errors/retries, and advances only on a confirmed receipt.
Changing `attemptId` resets answer and monotonic timing. Keep an attempt ID stable across retries;
cache emitted request bodies and retry those exact bodies rather than timing a second submission.
The answer slot receives `answer`, `disabled`, `submit` and `updateAnswer`; feedback gets `feedback`.

Default controls receive focus on a new attempt; server feedback transfers focus to the
preselected rating. Keyboard handlers live on the focused group, never on `document`; handled
events stop propagation and ignore repeat, IME and modifier chords. Choice controls lock after
feedback so a choice key cannot also select a rating. H requests a hint outside editable fields;
Escape requests an exit (the page owns confirmation), and Space on the focused shell frame
requests audio (the page owns playback). Native button Space activation is preserved.
All components are previewed under both token themes at `/dev/design`; grids collapse on mobile.

### Framework contract for the study shell (3.2.1)

Use generated `components['schemas']['AttemptRead']` and its `status` discriminator; do not
hand-write API shapes. Render `prompt.text`, `prompt.input`, `choices[{id,label}]` and optional
protected `media_id`; media IDs still require the authenticated blob adapter, not direct URLs.
Open attempts have no correctness/feedback/accepted forms. Hint requests use the persisted
`/hint` response; the shell must not synthesize `hint_used`.

On prompt display capture `performance.now()`. Submit `AttemptAnswer {answer, duration_ms}`
or `AttemptGiveUp {duration_ms}`, flooring the elapsed nonnegative milliseconds. Preserve the
same body for retries; a different answer/duration after grading is a conflict. Render only
the server's `feedback`, `auto_rating`, bounded `duration_ms` and `server_elapsed_ms`.
The rating bar may override any suggestion, including Easy for recognition. Send only
`AttemptConfirm {rating}` and advance after the confirmed receipt; answer submission alone
never updates the card. Retry the same confirmation after network uncertainty.

Handle `exercise.no_usable`, expiry, unavailable hints, hidden/removed membership and stale
attempt errors explicitly. Receipt-backed completed retries survive expiry; abandoned attempts
require a new issuance. Transport orchestration remains the study-page task; the shared controls
do not make API calls, import generators or expose their private answer specifications.
