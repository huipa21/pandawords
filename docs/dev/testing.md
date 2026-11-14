# Testing

## Layers

| Layer | Tool | Location | Covers |
|---|---|---|---|
| Unit (backend) | pytest | `backend/tests/unit` | Pure logic: auto-rating, plan pacing, lexicon parsing, ID encoding, distractor ranking |
| Integration | pytest + real SurrealDB 3.3 (port 8101) | `backend/tests/integration` | Repositories, migrations, owner isolation, graph queries |
| API | pytest + httpx `ASGITransport` | `backend/tests/api` | Endpoints, auth, error codes, cross-user access returns 404 |
| Unit (frontend) | vitest + @vue/test-utils | `frontend/src/**/*.test.ts` | Composables, stores, components with logic (RatingBar keys, SenseSelectList pre-check) |
| E2E | Playwright | `frontend/e2e` | Critical flows only, against the `dev.ps1 up` stack on `main` |

## Commands

`./scripts/dev.ps1 test` runs everything except E2E. `-Backend`, `-Frontend` and `-E2E` select one
layer, and selectors can combine (duplicates run only once). E2E is explicit only: it requires
the main worktree, a ready stack on 5173, and `frontend/playwright.config.ts`; a
missing config or tool fails rather than silently skipping tests. The hook runs
`pnpm exec playwright test`, using that config. `-UpdateSnapshot` requires the backend selector.
The output is quiet (`pytest -q`, vitest `dot` reporter). On failure it prints the full
failure output.

### First-login E2E

From `main`, run `.\scripts\dev.ps1 up`, then `.\scripts\dev.ps1 test -E2E`.
The runner imports the main worktree's `.env.dev`; both `ADMIN_USERNAME` and
`ADMIN_PASSWORD` must identify an enabled administrator whose initial password change
is already complete. Missing credentials fail the test without printing their values.
The existing API, worker, database, and Vite stack must remain running. Playwright uses
`http://localhost:5173` and never starts another stack.

Install the matching Chromium binary once from `frontend` with
`pnpm exec playwright install chromium` if Playwright reports that it is missing.
`pnpm test:e2e` runs the same test directly with the credentials already exported.
`pnpm exec playwright test --list` checks discovery without credentials or a running stack.
Only Chromium runs, with one worker, no retries, and no skipped/fallback cases.
Vitest's `src/**/*.test.ts` include keeps `e2e/**/*.spec.ts` out of unit runs.

The single flow selects English via the existing browser preference format, signs in as
the administrator, creates a unique `e2e_<UUID>` learner, reads the temporary-password
dialog, signs out, and signs in as that learner. It verifies the public forced-change
flag, the `/change-password` guard (including a direct `/projects` visit), then changes
the password and reaches Projects. API response types come from the generated schema.
Finally, the captured administrator token disables **only** the learner created by
this run, even after an assertion failure. The record remains in the dev database:
there is no delete API. An interrupted process or failed cleanup can leave an enabled
`e2e_` learner; an administrator must disable that specific account via User management.
Do not bulk-modify users or wipe the dev database to clean up these records.

Trace, video, and screenshots are off. Automatic error-context page snapshots are also
disabled via Playwright's `PLAYWRIGHT_NO_COPY_PROMPT` switch because the temporary-password
dialog contains a secret. Credential inputs avoid value-bearing `fill` call logs.
Do not enable debug/protocol logging, recording, or secret-bearing assertions when
running this flow. Normal Playwright reports/results remain gitignored.

## Test database

- The `test` command starts the in-memory SurrealDB container on 8101 if it isn't running.
- Each pytest session creates database `t_<worktree-short>_<random8>` in namespace `pandawords_test`
  and applies all migrations once. The database is removed at the end of the session.
- Tests isolate themselves by creating **fresh users** through factories. All user data is
  owner-scoped, and shared dictionary rows are deterministic and idempotent.
- Mark a test `@pytest.mark.fresh_db` when it needs an empty database (e.g. migration tests). It
  gets its own **unmigrated** database, removed after that test.
- The schema drift test applies the migrations to a fresh database and compares `INFO FOR DB`
  **and every `INFO FOR TABLE`** (including fields, indexes and events) with
  `backend/app/db/schema.snapshot.json`. JSON keys are sorted; schema definition strings are kept
  intact, and records, migration timestamps and random database names are not included.
- Normal test runs never rewrite the snapshot. Missing or changed snapshots fail with a unified
  diff (`committed` → `migrated`). Review the change, then run
  `.\scripts\dev.ps1 test -Backend -UpdateSnapshot` and commit the updated JSON alongside the new
  migration. The backend runner passes pytest's `--update-snapshot` flag explicitly.

## Fixtures

- `db`: async WebSocket connection to the migrated session database, or the empty database for
  a `fresh_db` test. `test_settings` selects the same database; `session_db` and
  `session_db_settings` explicitly access the shared migrated database.
- `app`: a test-configured FastAPI application with its real lifespan running. `client` is an
  async httpx client using that application through `ASGITransport`.
- `make_user`: typed async factory (`UserFactory`) using the auth service and repository, with
  unique usernames/IDs and real salted argon2id hashes on every call. Accepts keyword overrides
  for username, password, role, disabled and must-change-password. Its default test password is
  `test-password-123`. Do not share a single user between tests. Test settings supply test-only
  signing/bootstrap credentials; they never change the private development environment file.
- Auth service integration tests cover rotation/reuse, concurrent refresh on independent server
  connections, family-only revocation (including other-user isolation), logout, expiry, disabled
  users, and repeated/concurrent startup bootstrap. Readiness tests use the migrated harness
  database and its exact teardown rather than leaving ad hoc databases behind.
- Auth schema integration tests use `fresh_db`, apply the real migrations, and exercise username
  and token-hash uniqueness, field constraints and rotation metadata against the test server.
  Their opaque test password hashes are schema inputs, not usable login credentials. Teardown
  removes exactly each generated database; no dev database or shared test rows are modified.
- `job_db` / `job_settings` give each worker integration test its own migrated random database,
  preventing another test's queued jobs from interfering with global worker scans. Job tests
  synchronize candidate reads on two independent WebSocket connections before the conditional
  UPDATE, check scheduled exponential retries and their terminal limit, and exercise LIVE
  CREATE/UPDATE, socket loss/resubscription, polling without LIVE, and cancellation task cleanup.
  API tests verify owner-only status reads (shared jobs are not public), malformed opaque IDs,
  password-change gating and disabled accounts. No production services are started.
- Run unit tests from the selected worktree; it needs that worktree's backend environment
  (`uv sync --locked`) and frontend dependencies (`pnpm install --frozen-lockfile`).
- `lexicon_small.sqlite`: about 50 words (polysemy: *run*, *bank*; phrase: *kick the bucket*,
  *give up*; US/UK: *schedule*, *tomato*; derivation: *decide → decision*). It is built by the
  lexicon script from `backend/tests/fixtures/words.txt`.
- The DeepSeek client is faked in tests by default. No network access in unit, integration or API tests.

## What to test

Focused development-command guards (no shared dev ports or private environment changes):

```powershell
pwsh -NoProfile -File .\scripts\tests\lifecycle.Tests.ps1
pwsh -NoProfile -File .\scripts\tests\quality.Tests.ps1
pwsh -NoProfile -File .\scripts\tests\check-failure.Tests.ps1
pwsh -NoProfile -File .\scripts\tests\test-backend.Tests.ps1
```

The process test starts real tiny Node trees through native, cmd and actual pnpm launchers,
exercises stale/reused-PID guards and a
crashing launcher, and verifies all owned descendants disappear. The check test creates and
removes its own lint-error fixture and asserts nonzero exit plus Ruff's full failure diagnostic.

- Test behavior that a change introduces or fixes, with a few focused cases including edge cases.
- Always test owner isolation for new user-data endpoints.
- Don't test constants, re-exports, trivial accessors, framework behavior or markup snapshots.
- Coverage is not a goal.
