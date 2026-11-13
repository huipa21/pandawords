# Progress log

The main agent's working journal, edited on `main` only. Status per task lives in [PLAN.md](PLAN.md).
This file holds what the status column can't: the current run, blockers with reasons, discovered
backlog, and findings. Read it first when resuming ([../dev/workflow.md](../dev/workflow.md#resume-after-an-interruption)).

Durable knowledge goes to its topic doc (SurrealQL → [../dev/surrealdb-notes.md](../dev/surrealdb-notes.md),
design → ADR in [../decisions/](../decisions/)); the log entry just links to it.

## Current run

Request: —
Next step: —

| Task | Branch | Worktree | State / notes |
|---|---|---|---|

## Blocked

| Task | Blocked by (task, tool, decision) | Since | Notes |
|---|---|---|---|

## Backlog (discovered, not yet in PLAN.md)

| Found in | Item | Proposed home (task ID / new task) |
|---|---|---|

## Log

Newest first. One entry per finished or interrupted task: date, task, result, verification,
findings (with links), follow-ups.

<!-- ### YYYY-MM-DD — X.Y.Z Title
- Result: merged / blocked / partial
- Verified: `dev.ps1 check` ✅, `test -Backend` ✅
- Findings: …
- Follow-ups: → Backlog / Blocked -->
