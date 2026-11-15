"""Fixtures and helpers for project-import API tests (round trips through the real export)."""

import io
import json
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from httpx import AsyncClient, Response
from PIL import Image
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid, encode_rid
from app.db.migration_store import checked_query
from app.domain.bundle import parse_data
from app.domain.identity import user_key
from app.services.bundle_io import export_bundle, load_bundle
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory

PROJECT_FORMATS = frozenset({"pandawords.project"})
OWNED_TABLES = (
    "project",
    "includes",
    "note",
    "tag",
    "member_of",
    "lemma",
    "media",
    "memory",
    "review_log",
    "override",
)
SHARED_TABLES = ("lemma", "lexeme", "sense", "has_sense", "media")


@dataclass
class Dirs:
    root: Path
    media: Path
    work: Path


@dataclass
class Account:
    user: RecordID
    headers: dict[str, str]


@pytest.fixture
def test_settings(job_settings: Settings) -> Settings:
    return job_settings


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


@pytest.fixture(autouse=True)
def dirs(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Dirs]:
    with TemporaryDirectory(dir=Path.cwd(), prefix=".project-import-") as directory:
        root = Path(directory)
        found = Dirs(root, root / "media", root / "work")
        found.media.mkdir()
        monkeypatch.setattr(test_settings, "media_dir", found.media)
        monkeypatch.setattr(test_settings, "bundle_work_dir", found.work)
        yield found


@pytest.fixture
async def accounts(client: AsyncClient, make_user: UserFactory) -> AsyncIterator[list[Account]]:
    found: list[Account] = []
    for _ in range(2):
        created = await make_user()
        headers = bearer(await login(client, created.username))
        found.append(Account(RecordID("user", user_key(created.id)), headers))
    yield found


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 40, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


async def new_project(client: AsyncClient, account: Account, name: str) -> RecordID:
    response = await client.post("/api/projects", headers=account.headers, json={"name": name})
    assert response.status_code == 201, response.text
    return decode_rid(response.json()["id"], "project")


async def export(client: AsyncClient, account: Account, project: RecordID) -> bytes:
    response = await client.get(
        f"/api/projects/{encode_rid(project, 'project')}/export", headers=account.headers
    )
    assert response.status_code == 200, response.text
    return response.content


async def upload(
    client: AsyncClient, account: Account, content: bytes, include_progress: bool | None = None
) -> Response:
    params = {} if include_progress is None else {"include_progress": include_progress}
    return await client.post(
        "/api/projects/import",
        headers={**account.headers, "Content-Type": "application/gzip"},
        params=params,
        content=content,
    )


def rebuild(dirs: Dirs, archive: bytes, mutate: Callable[[dict[str, Any]], None]) -> bytes:
    """Re-pack an exported bundle after editing its JSON data (manifest stays valid)."""
    source = dirs.root / "source.tar.gz"
    source.write_bytes(archive)
    bundle = load_bundle(source, dirs.root, expected_formats=PROJECT_FORMATS)
    try:
        raw = bundle.data.model_dump(mode="json")
        mutate(raw)
        data = parse_data(json.dumps(raw).encode())
        header = bundle.archive.manifest.model_copy(update={"source": None})
        files = {m.file: bundle.media_path(m.file) for m in bundle.data.media}
        target = dirs.root / "rebuilt.tar.gz"
        target.unlink(missing_ok=True)
        export_bundle(target, header, data, files)
        return target.read_bytes()
    finally:
        bundle.close()


async def snapshot(db: AsyncWsSurrealConnection, *users: RecordID) -> dict[str, int]:
    """Row counts per owner and for shared rows; equal snapshots mean "no partial data"."""
    counts: dict[str, int] = {}
    for table in SHARED_TABLES:
        rows = await checked_query(
            db,
            "SELECT count() AS n FROM type::table($t) WHERE owner = NONE GROUP ALL;",
            {"t": table},
        )
        counts[f"shared.{table}"] = rows[0][0]["n"] if rows[0] else 0
    for user in users:
        for table in OWNED_TABLES:
            rows = await checked_query(
                db,
                "SELECT count() AS n FROM type::table($t) WHERE owner = $u GROUP ALL;",
                {"t": table, "u": user},
            )
            counts[f"{user.id}.{table}"] = rows[0][0]["n"] if rows[0] else 0
    return counts


def media_files(dirs: Dirs) -> set[Path]:
    return {path for path in dirs.media.rglob("*") if path.is_file()}
