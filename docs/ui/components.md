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
| `ExerciseShell` | Planned common frame: prompt/answer slots, server hint, submit/give up, feedback, hidden monotonic timer. Uses generated `AttemptRead`; emits answer + duration only, never client correctness |
| `ChoiceGrid` | 2–4 options for recognition exercises. Keys 1–4 select; Enter submits |
| `TypedAnswerInput` | Recall input. Accepts any valid form. Shows a diff highlight on a wrong answer |
| `RatingBar` | Again / Hard / Good / Easy in `--pw-rating-*` colors, with the auto-rating preselected. Keys 1–4; Space/Enter confirms |
| `ReviewProgress` | Done / remaining, new vs review counts |

### Framework contract for the study shell (3.2.1)

Use generated `components['schemas']['AttemptRead']` and its `status` discriminator; do not
hand-write API shapes. Render `prompt.text`, `prompt.input`, `choices[{id,label}]` and optional
protected `media_id`; media IDs still require the authenticated blob adapter, not direct URLs.
Open attempts have no correctness/feedback/accepted forms. Hint requests use the persisted
`/hint` response; the shell must not synthesize `hint_used`.

Recognition plugins (3.2.3) use the existing choice prompt shape. Render all 2–4 returned labels
in server order and submit the selected opaque `Choice.id`, not its label, position or a dictionary
record ID. IDs are new for every generated question; do not infer correctness or reuse old IDs.
Word-to-definition includes available accent/IPA in prompt text and remains usable without it.
Relation text specifies the stored relation type and direction; do not reinterpret an incoming edge
as an outgoing synonym/derivation. The open response contains no grading marker.

On prompt display capture `performance.now()`. Submit `AttemptAnswer {answer, duration_ms}`
or `AttemptGiveUp {duration_ms}`, flooring the elapsed nonnegative milliseconds. Preserve the
same body for retries; a different answer/duration after grading is a conflict. Render only
the server's `feedback`, `auto_rating`, bounded `duration_ms` and `server_elapsed_ms`.
The rating bar may override any suggestion, including Easy for recognition. Send only
`AttemptConfirm {rating}` and advance after the confirmed receipt; answer submission alone
never updates the card. Retry the same confirmation after network uncertainty.

Handle `exercise.no_usable`, expiry, unavailable hints, hidden/removed membership and stale
attempt errors explicitly. Receipt-backed completed retries survive expiry; abandoned attempts
require a new issuance. Concrete Vue shell implementation remains the study-UI task; these
transport contracts do not import generators or expose their private answer specifications.
