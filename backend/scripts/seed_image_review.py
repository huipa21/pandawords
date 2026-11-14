"""Mature exactly one isolated E2E learner's fixture card, without a runtime bypass."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from app.core.config import Settings
from app.db import auth
from app.db.client import database_lifespan
from app.db.study_plan_test_support import schedule
from app.services import projects, srs


async def seed(owner: str, project_id: str, sense_id: str) -> None:
    settings = Settings()
    if settings.app_env != "development" or urlsplit(settings.surreal_url).hostname not in {
        "localhost",
        "127.0.0.1",
    }:
        raise ValueError("The fixture seeder requires a local development database")
    async with database_lifespan(settings) as database:
        db = await database.get_connection()
        user = await auth.find_user(db, owner)
        if user is None or not user.username.startswith("e2e_image_") or user.role != "user":
            raise ValueError("Only an isolated image-review E2E learner may be seeded")
        project = await projects.read_project(db, owner, project_id)
        if not project.name.startswith("e2e-image-"):
            raise ValueError("Only the isolated image-review project may be seeded")
        memory = await srs.read_memory(db, owner, sense_id)
        await schedule(
            db,
            owner,
            memory,
            datetime.now(UTC) - timedelta(minutes=1),
            last_review=datetime.now(UTC) - timedelta(days=14),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner")
    parser.add_argument("project_id")
    parser.add_argument("sense_id")
    args = parser.parse_args()
    asyncio.run(seed(args.owner, args.project_id, args.sense_id))


if __name__ == "__main__":
    main()
