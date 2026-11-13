---
applyTo: "backend/**"
---

# Backend rules

- Python 3.14, async everywhere. Type everything; basedpyright must pass (`standard` mode, stricter where noted in `pyproject.toml`).
- Layers: `api/` (routers: thin, validation + auth deps) → `services/` (business logic) → `db/` (repositories, the only place with SurrealQL). Routers never import `db/` directly.
- `domain/` holds pydantic models. Naming: `XxxCreate`, `XxxUpdate`, `XxxRead`; internal records `Xxx`.
- Errors: raise domain exceptions from `core/errors.py`; one handler maps them to HTTP. Don't raise `HTTPException` from services.
- Config only via `core/config.py` (pydantic-settings). No `os.environ` elsewhere.
- Logging: `structlog.get_logger()`; log events as snake_case keys with context, never secrets or passwords.
- Auth dependency `current_user` is required on every non-public route; admin routes use `require_admin`.
- LLM calls go through `services/llm.py` only; callers must handle `LlmUnavailable` with a non-LLM fallback.
- Background work: enqueue a job via `services/jobs.py`; never block a request on external HTTP (lexicon audio, Pixabay, DeepSeek) longer than needed.
- Tests: `backend/tests/{unit,integration,api}`. Integration/API tests use the `db` fixture (fresh database on the test instance). Use the small lexicon fixture, never the full lexicon.
- Run `./scripts/dev.ps1 check` and `./scripts/dev.ps1 test -Backend` before committing.
