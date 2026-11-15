"""Convert owner-checked review histories into bounded, contiguous FSRS sequences."""

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from surrealdb import RecordID

from app.core.record_ids import encode_rid
from app.db.srs import user_record
from app.domain.srs import ReviewReceipt
from app.domain.srs_optimization import MAX_CARDS, MAX_LOGS, MAX_REVIEWS_PER_CARD


def _card_id(row: dict[str, Any], user: RecordID) -> str:
    memory = row["memory"]
    if (
        row.get("owner") != user
        or not isinstance(memory, RecordID)
        or memory.table_name != "memory"
    ):
        raise ValueError("Invalid memory owner or identity")
    parts = memory.id
    if not isinstance(parts, list) or len(parts) != 2 or parts[0] != user:
        raise ValueError("Invalid memory owner or identity")
    sense = parts[1]
    if not isinstance(sense, RecordID) or sense.table_name != "sense":
        raise ValueError("Invalid sense identity")
    return encode_rid(memory, "memory")


def _receipt(row: dict[str, Any], card_id: str, now: datetime) -> ReviewReceipt:
    receipt = ReviewReceipt.model_validate(row.get("receipt"))
    memory, project, at = row["memory"], row["project"], row["at"]
    last_review = receipt.memory.card.last_review
    identity = row.get("request_fingerprint")
    if (
        not isinstance(project, RecordID)
        or project.table_name != "project"
        or receipt.project_id != encode_rid(project, "project")
        or receipt.memory.id != card_id
        or receipt.memory.sense_id != encode_rid(memory.id[1], "sense")
        or not receipt.memory.introduced
        or not isinstance(at, datetime)
        or at.utcoffset() is None
        or at > now
        or receipt.at != at
        or last_review is None
        or last_review < at
        or last_review > now
        or not isinstance(row.get("attempt_id"), str)
        or not 1 <= len(row["attempt_id"]) <= 256
        or receipt.attempt_id != row["attempt_id"]
        or not isinstance(identity, str)
        or re.fullmatch(r"[0-9a-f]{64}", identity) is None
        or type(row.get("rating")) is not int
        or int(receipt.rating) != row["rating"]
        or type(row.get("auto_rating")) is not int
        or int(receipt.auto_rating) != row["auto_rating"]
        or type(row.get("correct")) is not bool
        or receipt.correct != row["correct"]
        or type(row.get("is_introduction")) is not bool
        or receipt.is_introduction != row["is_introduction"]
        or type(row.get("duration_ms")) is not int
        or not 0 <= row["duration_ms"] <= 60000
    ):
        raise ValueError("Invalid or outlier review")
    return receipt


def _review_time(receipt: ReviewReceipt) -> datetime:
    value = receipt.memory.card.last_review
    assert value is not None
    return value


def training_history(
    rows: list[dict[str, Any]], owner: str, now: datetime
) -> tuple[list[dict[str, Any]], int]:
    grouped: dict[str, list[tuple[dict[str, Any], ReviewReceipt]]] = defaultdict(list)
    invalid_cards: set[str] = set()
    excluded = 0
    user = user_record(owner)
    for row in rows:
        try:
            card_id = _card_id(row, user)
        except KeyError, TypeError, ValueError:
            excluded += 1
            continue
        try:
            grouped[card_id].append((row, _receipt(row, card_id, now)))
        except ValidationError, ValueError, KeyError, TypeError, IndexError, OverflowError:
            invalid_cards.add(card_id)
            excluded += 1

    sequences: list[list[tuple[dict[str, Any], ReviewReceipt]]] = []
    for card_id, reviews in sorted(grouped.items()):
        reviews.sort(key=lambda pair: _review_time(pair[1]))
        if (
            card_id in invalid_cards
            or (len(reviews) <= MAX_REVIEWS_PER_CARD and not reviews[0][1].is_introduction)
            or any(receipt.is_introduction for _, receipt in reviews[1:])
            or len({receipt.memory.card.last_review for _, receipt in reviews}) != len(reviews)
            or len({receipt.memory.card.card_id for _, receipt in reviews}) != 1
            or len({row["attempt_id"] for row, _ in reviews}) != len(reviews)
        ):
            excluded += len(reviews)
            continue
        excluded += max(0, len(reviews) - MAX_REVIEWS_PER_CARD)
        sequences.append(reviews[-MAX_REVIEWS_PER_CARD:])

    sequences.sort(key=lambda reviews: _review_time(reviews[-1][1]), reverse=True)
    excluded += sum(len(reviews) for reviews in sequences[MAX_CARDS:])
    sequences = sequences[:MAX_CARDS]
    selected: list[list[tuple[dict[str, Any], ReviewReceipt]]] = [[] for _ in sequences]
    selected_count = 0
    for index, reviews in enumerate(sequences):
        selected[index].extend(reviews[:2])
        selected_count += len(selected[index])
    for index, reviews in enumerate(sequences):
        available = MAX_LOGS - selected_count
        chosen = reviews[len(selected[index]) : len(selected[index]) + available]
        selected[index].extend(chosen)
        selected_count += len(chosen)
    excluded += sum(
        len(reviews) - len(chosen) for reviews, chosen in zip(sequences, selected, strict=True)
    )
    logs = []
    for card_id, reviews in enumerate(selected):
        for row, receipt in reviews:
            logs.append(
                {
                    "card_id": card_id,
                    "rating": row["rating"],
                    "review_datetime": _review_time(receipt).isoformat(),
                    "review_duration": row["duration_ms"],
                }
            )
    return logs, excluded


def eligible_transitions(
    logs: list[dict[str, Any]], *, since: datetime | None = None
) -> tuple[int, int]:
    previous: dict[int, datetime] = {}
    cards: set[int] = set()
    count = 0
    for log in logs:
        card = log["card_id"]
        at = datetime.fromisoformat(log["review_datetime"])
        if card in previous and (at - previous[card]).days > 0 and (since is None or at > since):
            count += 1
            cards.add(card)
        previous[card] = at
    return count, len(cards)
