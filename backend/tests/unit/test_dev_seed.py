from collections.abc import Iterator
from pathlib import Path
from shutil import rmtree
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.seed import apply_seeds, seed


async def test_empty_dev_seeds_do_not_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = AsyncMock(side_effect=AssertionError("Empty seeds must not access the database"))
    monkeypatch.setattr("app.db.seed.database_lifespan", connect)
    await seed(Settings(app_env="development"))
    connect.assert_not_called()
    with pytest.raises(ValueError, match="development-only"):
        await seed(Settings(app_env="production"))


@pytest.fixture
def seed_directory() -> Iterator[Path]:
    directory = Path(__file__).parents[3] / ".dev" / f"seed-test-{uuid4().hex}"
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        rmtree(directory)


async def test_seeds_run_in_order_and_can_repeat(seed_directory: Path) -> None:
    tmp_path = seed_directory
    for name in ("0002_second", "0001_first"):
        (tmp_path / f"{name}.py").write_text(f"async def up(db):\n    await db.query('{name}')\n")
    (tmp_path / "ignored.py").write_text("raise AssertionError('not a numbered seed')")
    db = AsyncMock()
    await apply_seeds(db, tmp_path)
    await apply_seeds(db, tmp_path)
    assert [call.args[0] for call in db.query.await_args_list] == [
        "0001_first",
        "0002_second",
        "0001_first",
        "0002_second",
    ]
    (tmp_path / "0003_invalid.py").write_text("def up(db): pass")
    with pytest.raises(ValueError, match="async def up"):
        await apply_seeds(db, tmp_path)
