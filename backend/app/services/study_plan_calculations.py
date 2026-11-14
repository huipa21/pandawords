"""Pure UTC pacing, actual-card forecasts and completed-history statistics."""

from collections import deque
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

from fsrs import Scheduler

from app.core.record_ids import decode_rid
from app.domain.projects import ProjectPlan
from app.domain.srs import MemoryRead
from app.domain.study_plan import CompletedCounts, ExamPacing, ForecastDay, StudyQueueItem


def utc_now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("Planning time must be timezone aware")
    return value.astimezone(UTC)


def completed_counts(
    logs: list[dict[str, Any]], now: datetime, project_id: str | None = None
) -> CompletedCounts:
    project = decode_rid(project_id, "project") if project_id else None
    today = [
        log
        for log in logs
        if log["at"].astimezone(UTC).date() == now.date()
        and (project is None or log["project"] == project)
    ]
    return CompletedCounts(
        new=sum(bool(log["is_introduction"]) for log in today),
        reviews=sum(not log["is_introduction"] for log in today),
    )


def exam_pacing(
    plan: ProjectPlan, remaining: int, completed_new: int, now: datetime
) -> ExamPacing | None:
    exam = plan.exam_date
    if exam is None:
        return None

    def windows(instant: datetime) -> int:
        if instant <= now:
            return 0
        days = (instant.date() - now.date()).days
        return days + int(instant.time() != datetime.min.time()) if days else 1

    def capacity(instant: datetime) -> int:
        days = windows(instant)
        return max(0, plan.daily_new - completed_new) + plan.daily_new * (days - 1) if days else 0

    days = windows(exam)
    divisor = max(1, days - 7)
    suggestion = min(plan.daily_new, (remaining + divisor - 1) // divisor)
    available, buffer = capacity(exam), capacity(exam - timedelta(days=7))
    return ExamPacing(
        remaining_new=remaining,
        days_left=days,
        suggested_daily_new=suggestion,
        capacity=available,
        buffer_capacity=buffer,
        impossible=remaining > available,
        buffer_at_risk=remaining > buffer,
    )


def forecast(cards: list[MemoryRead], now: datetime) -> list[ForecastDay]:
    days = [now.date() + timedelta(days=index) for index in range(7)]
    counts = dict.fromkeys(days, 0)
    for card in cards:
        if card.introduced:
            day = max(now.date(), card.card.due.astimezone(UTC).date())
            if day in counts:
                counts[day] += 1
    return [ForecastDay(date=day, due=counts[day]) for day in days]


def queue(
    cards: list[MemoryRead], plan: ProjectPlan, today: CompletedCounts, now: datetime
) -> list[StudyQueueItem]:
    scheduler = Scheduler()

    def retrievability(memory: MemoryRead) -> float | None:
        if (
            not memory.card.stability
            or memory.card.stability < 0
            or memory.card.last_review is None
        ):
            return None
        try:
            value = scheduler.get_card_retrievability(memory.card.to_card(), now)
            return value if isfinite(value) and 0 <= value <= 1 else None
        except ValueError, TypeError, ArithmeticError, OverflowError:
            return None

    due = [
        StudyQueueItem(kind="review", memory=card, retrievability=retrievability(card))
        for card in cards
        if card.introduced and card.card.due <= now
    ]
    due.sort(
        key=lambda item: (
            item.retrievability if item.retrievability is not None else 0,
            item.memory.card.due,
            item.memory.sense_id,
        )
    )
    if plan.review_cap is not None:
        due = due[: max(0, plan.review_cap - today.reviews)]
    new = [StudyQueueItem(kind="new", memory=card) for card in cards if not card.introduced]
    return due + new[: max(0, plan.daily_new - today.new)]


def history_statistics(logs: list[dict[str, Any]], now: datetime) -> tuple[float | None, int]:
    start = now.date() - timedelta(days=29)
    recent = [log for log in logs if start <= log["at"].astimezone(UTC).date() <= now.date()]
    retention = sum(bool(log["correct"]) for log in recent) / len(recent) if recent else None
    dates = {log["at"].astimezone(UTC).date() for log in logs}
    end = now.date() if now.date() in dates else now.date() - timedelta(days=1)
    streak = 0
    while end in dates:
        streak += 1
        end -= timedelta(days=1)
    return retention, streak


def available_new_count(projects: list[tuple[list[MemoryRead], int]]) -> int:
    """Match shared cards to project allowances without counting a card twice."""
    eligible: dict[str, list[int]] = {}
    slots: list[set[str]] = [set() for _ in projects]
    for index, (cards, allowance) in enumerate(projects):
        if allowance:
            for card in cards:
                if not card.introduced:
                    eligible.setdefault(card.id, []).append(index)
    for initial in eligible:
        pending = deque([initial])
        parents: dict[str, tuple[str, int] | None] = {initial: None}
        visited: set[int] = set()
        found = False
        while pending and not found:
            current = pending.popleft()
            for index in eligible[current]:
                if index in visited:
                    continue
                visited.add(index)
                if len(slots[index]) < projects[index][1]:
                    slots[index].add(current)
                    while (parent := parents[current]) is not None:
                        previous, previous_index = parent
                        slots[previous_index].remove(current)
                        slots[previous_index].add(previous)
                        current = previous
                    found = True
                    break
                for assigned in sorted(slots[index]):
                    if assigned not in parents:
                        parents[assigned] = (current, index)
                        pending.append(assigned)
    return sum(len(slot) for slot in slots)
