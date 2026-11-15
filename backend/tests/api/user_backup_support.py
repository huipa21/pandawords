"""Helpers for user backup/restore API tests (real export -> restore round trips)."""

import json
from collections.abc import Callable
from typing import Any

from httpx import AsyncClient, Response
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.db.migration_store import checked_query
from app.domain.bundle import parse_data
from app.domain.bundle_manifest import ManifestHeader
from app.services.bundle_io import LoadedBundle, export_bundle, load_bundle
from app.services.lexicon import LexiconReader
from tests.api.project_export_support import include
from tests.api.project_import_support import Account, Dirs, Seeded, new_project, seed

USER_FORMATS = frozenset({"pandawords.user"})
PREFS: dict[str, Value] = {
    "theme": "dark",
    "locale": "en",
    "accent": "UK",
    "review_images_enabled": False,
    "review_audio_enabled": True,
    "desired_retention": 0.85,
}
# Every table that can hold rows owned by a user (wiped to simulate data loss).
USER_TABLES = (
    "includes",
    "member_of",
    "used_in",
    "relates_to",
    "review_log",
    "memory",
    "override",
    "note",
    "media",
    "project",
    "tag",
    "sentence",
    "sense",
    "lexeme",
    "lemma",
    "restore_receipt",
    "srs_optimization",
)


async def backup(client: AsyncClient, account: Account) -> bytes:
    response = await client.get("/api/me/backup", headers=account.headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/gzip"
    assert ".pandawords-user.tar.gz" in response.headers["content-disposition"]
    return response.content


async def restore(
    client: AsyncClient, account: Account, content: bytes, include_progress: bool | None = None
) -> Response:
    params = {} if include_progress is None else {"include_progress": include_progress}
    return await client.post(
        "/api/me/restore",
        headers={**account.headers, "Content-Type": "application/gzip"},
        params=params,
        content=content,
    )


def open_user(dirs: Dirs, archive: bytes) -> LoadedBundle:
    source = dirs.root / "backup.tar.gz"
    source.write_bytes(archive)
    return load_bundle(source, dirs.root, expected_formats=USER_FORMATS)


def rebuild_user(dirs: Dirs, archive: bytes, mutate: Callable[[dict[str, Any]], None]) -> bytes:
    bundle = open_user(dirs, archive)
    try:
        raw = bundle.data.model_dump(mode="json")
        mutate(raw)
        data = parse_data(json.dumps(raw).encode())
        header = ManifestHeader(**bundle.archive.manifest.model_dump(exclude={"entries", "source"}))
        files = {m.file: bundle.media_path(m.file) for m in bundle.data.media}
        target = dirs.root / "rebuilt.tar.gz"
        target.unlink(missing_ok=True)
        export_bundle(target, header, data, files)
        return target.read_bytes()
    finally:
        bundle.close()


def drop_owned_lemmas(raw: dict[str, Any]) -> None:
    """Remove owned lemmas (globally unique text) so another account can restore the rest."""
    refs = {r["ref"] for r in raw["records"] if r["table"] == "lemma" and r["owner"] == "owned"}
    raw["records"] = [r for r in raw["records"] if r["ref"] not in refs]
    raw["edges"] = [e for e in raw["edges"] if e["from_"] not in refs and e["to"] not in refs]
    raw["includes"] = [i for i in raw["includes"] if i["target"] not in refs]
    raw["notes"] = [n for n in raw["notes"] if n["target"] not in refs]
    raw["overrides"] = [o for o in raw["overrides"] if o["target"] not in refs]


async def rows(db: AsyncWsSurrealConnection, query: str, **variables: Any) -> list[dict[str, Any]]:
    return (await checked_query(db, query, variables))[0]


async def set_prefs(db: AsyncWsSurrealConnection, user: RecordID, prefs: dict[str, Value]) -> None:
    await checked_query(db, "UPDATE $u SET prefs = $p;", {"u": user, "p": prefs})


async def account_row(db: AsyncWsSurrealConnection, user: RecordID) -> dict[str, Any]:
    return (await rows(db, "SELECT * FROM $u;", u=user))[0]


async def wipe(db: AsyncWsSurrealConnection, user: RecordID) -> None:
    """Simulate losing all of a user's data (account row kept)."""
    for table in USER_TABLES:
        await checked_query(db, "DELETE type::table($t) WHERE owner = $u;", {"t": table, "u": user})


async def seed_user(
    client: AsyncClient,
    db: AsyncWsSurrealConnection,
    alice: Account,
    reader: LexiconReader,
    dirs: Dirs,
) -> tuple[Seeded, RecordID]:
    """The project-import fixture plus a second project and customized preferences."""
    seeded = await seed(client, db, alice, reader, dirs)
    second = await new_project(client, alice, "Second")
    await include(db, alice.user, second, seeded.words.flow, study_order=2)
    await set_prefs(db, alice.user, PREFS)
    return seeded, second
