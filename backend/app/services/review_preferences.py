from surrealdb import AsyncSurrealConnection

from app.db import review_preferences as repository
from app.domain.review_preferences import ReviewPreferences, ReviewPreferencesUpdate


async def read(db: AsyncSurrealConnection, owner: str) -> ReviewPreferences:
    return await repository.preferences(db, owner)


async def update(
    db: AsyncSurrealConnection, owner: str, data: ReviewPreferencesUpdate
) -> ReviewPreferences:
    return await repository.preferences(db, owner, data)
