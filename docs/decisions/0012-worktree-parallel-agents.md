# 0012 — Numbered plan, worktree per task, parallel agents

**Status:** Accepted (2026-11-13)

**Context.** Work runs across many separate agent sessions. The owner triggers work with "implement
task X.Y.Z" and wants independent work to run in parallel.

**Decision.**
- `docs/plans/PLAN.md` numbers every task `phase.epic.task` and lists its dependencies, parallel
  waves and status. `phase-N.md` holds the details and acceptance criteria.
- Each task gets a branch `task/X.Y.Z-slug` and a worktree at `../pandawords.worktrees/X.Y.Z`.
  Independent tasks run in parallel sub-agents.
- The main agent merges into `main` with `--no-ff` one at a time, re-checking after each merge. It
  then removes the worktree folder and the branch, and is the only one that updates the plan status.

**Consequences.** Sessions can be resumed from the plan alone. Parallel agents can't edit the same
files or the plan. Shared resources (env, lexicon, test DB) are set up so they work across worktrees
(docs/dev/workflow.md).
