from surrealdb import AsyncSurrealConnection
from surrealdb.types import Value

from app.core.errors import AppError
from app.db.auth import _rows
from app.db.srs import user_record
from app.domain.review_preferences import ReviewPreferences, ReviewPreferencesUpdate


async def preferences(
    db: AsyncSurrealConnection,
    owner: str,
    update: ReviewPreferencesUpdate | None = None,
) -> ReviewPreferences:
    params: dict[str, Value] = {"user": user_record(owner)}
    if update is None:
        query = "SELECT prefs FROM $user WHERE id = $user;"
    else:
        params.update(update.model_dump(exclude_unset=True))
        # Fixed assignments keep partial updates atomic without replacing unrelated prefs.
        params.update(
            images="review_images_enabled" in update.model_fields_set,
            audio="review_audio_enabled" in update.model_fields_set,
            accent_set="accent" in update.model_fields_set,
        )
        params.setdefault("review_images_enabled", True)
        params.setdefault("review_audio_enabled", True)
        params.setdefault("accent", "US")
        query = (
            "UPDATE $user SET "
            "prefs.review_images_enabled = IF $images THEN $review_images_enabled "
            "ELSE prefs.review_images_enabled END, "
            "prefs.review_audio_enabled = IF $audio THEN $review_audio_enabled "
            "ELSE prefs.review_audio_enabled END, "
            "prefs.accent = IF $accent_set THEN $accent ELSE prefs.accent END "
            "WHERE id = $user RETURN AFTER;"
        )
    rows = await _rows(db, query, params)
    if not rows:
        raise AppError("auth.invalid_credentials", 401, "User not found.")
    prefs = rows[0]["prefs"]
    return ReviewPreferences.model_validate(
        {key: prefs[key] for key in ReviewPreferences.model_fields if key in prefs}
    )
