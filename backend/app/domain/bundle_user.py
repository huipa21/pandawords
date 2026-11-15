"""Typed bundle entries for owner-owned learning data (projects, overlays, media, progress)."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue

from app.domain.bundle_edges import Entry, Instant, Int, Lang, NonNegative, Ref, Scope, Short, Text
from app.domain.media import MediaKind, MediaSource

SHA256_PATTERN = r"^[0-9a-f]{64}$"
MEDIA_FILE_PATTERN = r"^media/[0-9a-f]{64}\.(?:mp3|ogg|wav|m4a|webm|jpg|png|webp|gif)$"

type Sha256 = Annotated[str, Field(pattern=SHA256_PATTERN)]
type Rating = Annotated[int, Field(ge=1, le=4)]


class Plan(Entry):
    daily_new: NonNegative
    exam_date: Instant | None = None
    review_cap: NonNegative | None = None


class ProjectEntry(Entry):
    ref: Ref
    name: Annotated[str, Field(min_length=1, max_length=128)]
    description: Annotated[str, Field(max_length=10_000)]
    target_lang: Annotated[str, Field(min_length=1, max_length=35)]
    source_lang: Annotated[str, Field(min_length=1, max_length=35)]
    plan: Plan
    created_at: Instant


class IncludeEntry(Entry):
    """Project membership; ``hidden`` and ``study_order`` carry visibility and sense order."""

    project: Ref
    target: Ref
    hidden: bool
    added_at: Instant
    study_order: NonNegative | None = None


class OverrideEntry(Entry):
    target: Ref
    fields: Annotated[dict[Short, JsonValue], Field(max_length=64)]
    updated_at: Instant


class NoteEntry(Entry):
    ref: Ref
    target: Ref
    kind: Literal["note", "mnemonic"]
    text: Text


class MediaEntry(Entry):
    """Media metadata; bytes live at ``file`` inside the archive, never a storage path."""

    ref: Ref
    owner: Scope
    target: Ref
    kind: MediaKind
    mime: Short
    source: MediaSource
    attribution: Annotated[str, Field(max_length=4000)] | None = None
    accent: Literal["US", "UK"] | None = None
    file: Annotated[str, Field(pattern=MEDIA_FILE_PATTERN)]


class Card(Entry):
    card_id: Int
    state: Annotated[int, Field(ge=1, le=3)]
    step: NonNegative | None = None
    stability: float | None = None
    difficulty: float | None = None
    due: Instant
    last_review: Instant | None = None


class MemoryEntry(Entry):
    """One FSRS card per sense; the memory ID is rebuilt from the importer and sense."""

    sense: Ref
    card: Card
    introduced: bool


class ReviewLogEntry(Entry):
    """Completed review. Source receipts/fingerprints embed database IDs and are not exported;
    ``card_after`` keeps the resulting card so an importer can rebuild a receipt."""

    sense: Ref
    project: Ref | None
    exercise: Annotated[str, Field(min_length=1, max_length=128)]
    rating: Rating
    auto_rating: Rating
    correct: bool
    hint_used: bool
    duration_ms: Annotated[int, Field(ge=0, le=60_000)]
    at: Instant
    is_introduction: bool
    attempt_id: Annotated[str, Field(min_length=1, max_length=256)]
    card_after: Card | None = None


class Preferences(Entry):
    """Learning/display preferences only; account, role and credentials are never exported."""

    theme: Literal["system", "light", "dark"]
    locale: Annotated[str, Field(min_length=1, max_length=35)]
    accent: Literal["US", "UK"]
    desired_retention: Annotated[float, Field(gt=0, lt=1)]
    review_images_enabled: bool
    review_audio_enabled: bool
    source_lang: Lang
    target_lang: Lang
