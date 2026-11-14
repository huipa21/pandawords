"""Development-only, repeatable seeds; the Phase 1 seed folder is intentionally empty."""

import asyncio
import importlib.util
import inspect
from pathlib import Path

from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.db.client import database_lifespan

SEEDS = Path(__file__).with_name("seeds")


def discover(directory: Path) -> list[Path]:
    return sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.py"))


async def apply_seeds(db: AsyncSurrealConnection, directory: Path) -> None:
    for path in await asyncio.to_thread(discover, directory):
        spec = importlib.util.spec_from_file_location(f"_dev_seed_{path.stem}", path)
        if spec is None:
            raise ValueError(f"Cannot load development seed {path.name}")
        module = importlib.util.module_from_spec(spec)
        content = await asyncio.to_thread(path.read_bytes)
        exec(compile(content, str(path), "exec"), module.__dict__)
        up = getattr(module, "up", None)
        if not inspect.iscoroutinefunction(up):
            raise ValueError(f"Development seed {path.name} requires async def up(db)")
        await up(db)


async def seed(settings: Settings, directory: Path = SEEDS) -> None:
    if settings.app_env != "development":
        raise ValueError("Seeds are development-only")
    if not await asyncio.to_thread(discover, directory):
        return
    async with database_lifespan(settings) as database:
        await apply_seeds(await database.get_connection(), directory)


if __name__ == "__main__":
    asyncio.run(seed(Settings()))
