# 0002 — Shared dictionary + per-user overlay

**Status:** Accepted (2026-11-13)

**Context.** Many users add the same words. Users must be able to edit anything and hide senses
without affecting each other.

**Decision.** Canonical lemmas, lexemes, senses and relations are stored once (`owner = NONE`,
deterministic IDs). Per-user data sits on top: `override` (edits per user), `includes.hidden`
(hiding per project), user-owned rows and edges (`owner = user`), notes, media and memory. Every
read filters `owner = NONE OR owner = $user` and applies overrides.

**Consequences.** No duplication, and dictionary improvements reach everyone. Reads are more complex
(override merge, owner filter), so they're centralized in repository functions and covered by
isolation tests. Imports merge by deterministic ID.
