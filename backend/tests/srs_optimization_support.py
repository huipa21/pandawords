from datetime import UTC, datetime, timedelta
from typing import Any

from fsrs import Card, Rating
from surrealdb import RecordID

from app.core.record_ids import encode_rid
from app.db.srs import user_record
from app.domain.srs import CardState, MemoryRead, ReviewReceipt


def history(
    owner: str,
    *,
    cards: int = 10,
    reviews: int = 11,
    start: datetime | None = None,
    interval: timedelta = timedelta(days=2),
    inverted: bool = False,
) -> list[dict[str, Any]]:
    user = user_record(owner)
    start = start or datetime.now(UTC) - timedelta(days=200)
    rows = []
    for card_id in range(cards):
        sense = RecordID("sense", f"optimization-{card_id}")
        memory = RecordID("memory", [user, sense])
        project = RecordID("project", "optimization")
        for index in range(reviews):
            at = start + interval * index
            failed = (index + int(inverted)) % 4 == 3
            card = Card(card_id=card_id, due=at + timedelta(days=2), last_review=at)
            receipt = ReviewReceipt(
                attempt_id=f"{card_id}-{index}",
                project_id=encode_rid(project, "project"),
                memory=MemoryRead(
                    id=encode_rid(memory, "memory"),
                    sense_id=encode_rid(sense, "sense"),
                    introduced=True,
                    card=CardState.from_card(card),
                ),
                auto_rating=Rating.Good,
                rating=Rating.Again if failed else Rating.Good,
                correct=not failed,
                at=at,
                is_introduction=index == 0,
            )
            rows.append(
                {
                    "owner": user,
                    "memory": memory,
                    "project": project,
                    "exercise": "recall",
                    "correct": receipt.correct,
                    "hint_used": False,
                    "duration_ms": 1000,
                    "auto_rating": 3,
                    "rating": int(receipt.rating),
                    "at": at,
                    "is_introduction": index == 0,
                    "attempt_id": receipt.attempt_id,
                    "request_fingerprint": "a" * 64,
                    "receipt": receipt.model_dump(mode="json"),
                }
            )
    return rows
