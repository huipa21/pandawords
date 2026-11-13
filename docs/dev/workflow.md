# Task workflow (agents)

The user triggers work with **"implement task X.Y.Z"**. Other accepted forms are an epic
(`implement 1.4` = all of its tasks), a wave (`implement phase 1 wave 3`) or a list
(`implement 1.2.1, 1.4.1`).

## 1. Prepare (main agent, in the main worktree on `main`)

1. `git status` must be clean on `main`. If it isn't, stop and report.
2. Read the task rows in [../plans/PLAN.md](../plans/PLAN.md) and the details in `../plans/phase-N.md`.
   If the phase file has no detail for the task, ask the user before writing it (AGENTS.md rule 11).
3. Check the dependencies: every `Depends on` task must be ✅. If not, stop, list the blockers and
   record them under **Blocked** in [../plans/PROGRESS.md](../plans/PROGRESS.md). Missing tools or
   undecided design questions go there too.
4. Build the execution set: order the requested tasks by dependency into waves. Tasks in the same
   wave run **in parallel**.
5. Mark each task in the set 🟡 in `PLAN.md`, fill **Current run** in `PROGRESS.md` (request,
   task → branch/worktree, next step), and commit both on `main` with `docs(plan): start X.Y.Z`
   before creating worktrees. This is what lets an interrupted run be resumed.
   (Exception: 1.1.1 creates the repo, so it's done directly on `main` and marked ✅ when it's committed.)

## 2. Execute — parallel by default

**Mode A: several independent tasks.** Use one branch, one worktree and one sub-agent per task:

```powershell
git worktree add ..\pandawords.worktrees\X.Y.Z -b task/X.Y.Z-short-slug main
```

**Mode B: one task with independent parts** (e.g. backend API + frontend page). Use one worktree.
Sub-agents get **disjoint file scopes** and don't commit. The main agent integrates, checks and commits.

Do the work directly (no sub-agents) when it is sequential or small (about five tool calls or fewer).

### Sub-agent brief (always include)

- Task ID and title, the detail text and acceptance criteria copied from `phase-N.md`
- Worktree path and branch, and the file scope it may touch
- Docs to read (only those named in the task's `Docs` line), plus AGENTS.md hard rules
- Done when: acceptance criteria met, `./scripts/dev.ps1 check` and the relevant `test` pass,
  related docs updated, changes committed on the task branch (Mode A)
- Don'ts: don't edit `docs/plans/PLAN.md` or `docs/plans/PROGRESS.md`, don't merge, don't run `dev.ps1 up` (ports are shared),
  don't touch files outside the scope
- Return: a summary of changes, files touched, commands run with their results, findings, and
  open issues (missing dependencies, out-of-scope work found). The main agent records them in PROGRESS.md.

## 3. Integrate (main agent)

For each finished task branch, one at a time, in dependency order:

```powershell
git switch main
git merge --no-ff task/X.Y.Z-short-slug -m "merge: task X.Y.Z <title>"
./scripts/dev.ps1 check; ./scripts/dev.ps1 test    # must pass before the next merge
```

If there's a conflict, resolve it on `main` and keep both intents. If that's unclear, stop and ask.

## 4. Clean up (after each successful merge)

```powershell
git branch --merged main | Select-String "task/X.Y.Z"          # confirm merged
git worktree remove --force ..\pandawords.worktrees\X.Y.Z       # ignored files (node_modules, .venv) need --force
git branch -d task/X.Y.Z-short-slug
if (Test-Path ..\pandawords.worktrees\X.Y.Z) { Remove-Item -Recurse -Force ..\pandawords.worktrees\X.Y.Z }
git worktree prune
```

If removal fails because a file is locked, stop the processes started from that folder (by PID)
and retry. Confirm with `git worktree list` that only the main worktree remains.

## 5. Close out

- Update the status column in `PLAN.md` (✅) on `main`. In `PROGRESS.md`, remove the task from
  **Current run**, add a **Log** entry (result, verification, findings, follow-ups), and move the
  sub-agent's open issues to **Backlog** or **Blocked**. Commit both with `docs(plan): mark X.Y.Z done`.
- Backlog items become PLAN.md tasks only after the user agrees; then remove them from Backlog.
- Report to the user: what was done, verification results, and the next ready tasks (dependencies
  now satisfied).
- Push to GitHub only when the user asks.

## Resume after an interruption

Progress lives in `PLAN.md` (status), [../plans/PROGRESS.md](../plans/PROGRESS.md) (current run,
blockers, backlog, log) and git state. When the user says "resume" (or a session restarts mid-task):

0. Read **Current run** and **Blocked** in `PROGRESS.md`.
1. `git status` on `main`. If it's dirty, an integration step was interrupted: inspect it, finish
   or abort the merge (`git merge --abort`), then continue.
2. List 🟡 tasks in `PLAN.md`. For each, check its git state:
   `git worktree list`, `git branch --list "task/*"`, `git log main..task/X.Y.Z-slug --oneline`.

   | State | Action |
   |---|---|
   | Branch merged into `main` | Run step 4 (clean up) and step 5 (mark ✅) |
   | Branch has commits, not merged | Review the diff against the acceptance criteria; finish if needed, then step 3 |
   | Worktree exists, uncommitted or no commits | Re-brief a sub-agent on the same worktree, telling it what's already there |
   | No branch/worktree | Restart the task from step 2 |
3. Update **Current run** to match what you found, commit, then continue with the remaining tasks
   of the original request (for Phase 1, use
   [../plans/phase-1-waves.md](../plans/phase-1-waves.md) to find the next ready tasks).

## Shared resources across worktrees

| Resource | Handling |
|---|---|
| `.env.dev` | Gitignored. Scripts load it from the **main worktree root** (`git rev-parse --git-common-dir` → parent) |
| `data/lexicon`, `data/media` | Absolute paths in `.env.dev`, so all worktrees share them |
| Python venv / node_modules | Per worktree. uv and pnpm caches make installs fast |
| Test DB (8101) | Shared instance; each test session uses its own database name (see testing.md) |
| Dev DB (8100), ports 8000/5173 | Main worktree only. Sub-agents don't run `up` or E2E |
| E2E tests | Run by the main agent on `main` after merging |
