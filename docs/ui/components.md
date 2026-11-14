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
| `PageHeader` | `title`, `subtitle?`, `back?`; `actions` slot |
| `EmptyState` | Wraps NEmpty. `icon`, `titleKey`, `descKey?`; `action` slot |
| `ErrorState` | Wraps NResult with retry. `error`, `@retry` |
| `ConfirmAction` | Wraps a destructive action with a dialog. `titleKey`, `contentKey`, `@confirm` |
| `ThemeToggle` | Implemented: accessible icon button cycles system → light → dark; persists via preferences store |
| `LocaleSwitch` | Implemented: accessible icon button toggles zh-CN / en, including Naive locale and document language |
| `JobStatus` | Inline progress for background jobs. `jobId` or `jobs[]` |
| `SourceAttribution` | License attribution line for dictionary content |

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
| `LemmaTree` | Project tree (NTree with custom render of WordHeader, LexemeBlock, SenseItem). `projectId` |
| `NoteEditor` | Note or mnemonic for any target. `target`, `kind` |

## Graph components (`src/components/graph/`)

| Component | Purpose / key props |
|---|---|
| `GraphCanvas` | Cytoscape wrapper. `elements`, `layout: 'fcose'\|'dagre'`, `focusId?`. Emits `select`, `expand`. Styles come from `cytoscape-style.ts` (tokens) and rebuild on theme change |
| `GraphLegend` | Node and edge legend from tokens. Toggles filters |
| `GraphToolbar` | Layout switch, depth, filters (node types, relation types), fit, search |

## Exercise components (`src/components/exercise/`)

| Component | Purpose / key props |
|---|---|
| `ExerciseShell` | Common frame: prompt slot, answer slot, hint, submit, feedback, timer (hidden). Emits `answered {correct, durationMs, usedHint, answer}` |
| `ChoiceGrid` | 2–4 options for recognition exercises. Keys 1–4 select; Enter submits |
| `TypedAnswerInput` | Recall input. Accepts any valid form. Shows a diff highlight on a wrong answer |
| `RatingBar` | Again / Hard / Good / Easy in `--pw-rating-*` colors, with the auto-rating preselected. Keys 1–4; Space/Enter confirms |
| `ReviewProgress` | Done / remaining, new vs review counts |
