# 0009 — No CI; local build, manual deploy

**Status:** Accepted (2026-11-13)

**Context.** Building on the 2 vCPU / 4 GB server would compete with the running apps. The owner
prefers no GitHub Actions.

**Decision.** All checks run locally (`dev.ps1 check/test`, lefthook pre-commit). Releases are built
on the Windows laptop with Podman for `linux/amd64`, saved as gzipped docker-archives, copied to the
server, and loaded with `docker load`. The server runs Docker Compose behind the existing Caddy
container. GitHub is used only as a remote.

**Consequences.** Keeping quality depends on running the local checks, which the workflow makes part
of every task's definition of done.
