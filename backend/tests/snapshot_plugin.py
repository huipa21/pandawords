"""Explicit snapshot updates; ordinary test runs only compare committed metadata."""

from __future__ import annotations

from difflib import unified_diff
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-snapshot",
        action="store_true",
        default=False,
        help="Rewrite the schema snapshot after applying migrations to a fresh test database",
    )


@pytest.fixture
def update_snapshot(pytestconfig: pytest.Config) -> bool:
    return bool(pytestconfig.getoption("--update-snapshot"))


def assert_snapshot(actual: str, path: Path, *, update: bool = False) -> None:
    if update:
        path.write_text(actual, encoding="utf-8", newline="\n")
        return
    expected = path.read_text(encoding="utf-8") if path.exists() else ""
    if actual != expected:
        diff = "".join(
            unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=f"{path.name} (committed)",
                tofile=f"{path.name} (migrated)",
            )
        )
        pytest.fail(
            "Schema snapshot drift detected:\n"
            f"{diff}\n"
            "Review the schema change, then run "
            r".\scripts\dev.ps1 test -Backend -UpdateSnapshot and commit the snapshot.",
            pytrace=False,
        )
