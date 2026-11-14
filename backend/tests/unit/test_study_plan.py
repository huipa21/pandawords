from datetime import UTC, datetime, timedelta, timezone

import pytest
from fsrs import State
from surrealdb import RecordID

from app.core.record_ids import encode_rid
from app.domain.projects import ProjectPlan
from app.domain.srs import CardState, MemoryRead
from app.domain.study_plan import CompletedCounts
from app.services.study_plan_calculations import (
    available_new_count,
    exam_pacing,
    forecast,
    history_statistics,
    queue,
)

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


def card(
    name: str,
    *,
    introduced: bool = True,
    due: datetime = NOW,
    stability: float | None = 10,
    elapsed: int = 10,
) -> MemoryRead:
    return MemoryRead(
        id=name,
        sense_id=name,
        introduced=introduced,
        card=CardState(
            card_id=1,
            state=State.Review,
            stability=stability,
            difficulty=5,
            due=due,
            last_review=NOW - timedelta(days=elapsed) if introduced else None,
        ),
    )


@pytest.mark.parametrize(
    (
        "remaining",
        "daily",
        "exam",
        "done",
        "days",
        "suggestion",
        "capacity",
        "buffer",
        "impossible",
        "risk",
    ),
    [
        (20, 10, NOW + timedelta(days=11), 0, 12, 4, 120, 50, False, False),
        (20, 3, NOW + timedelta(days=9), 0, 10, 3, 30, 9, False, True),
        (40, 3, NOW + timedelta(days=9), 0, 10, 3, 30, 9, True, True),
        (20, 0, NOW + timedelta(days=11), 0, 12, 0, 0, 0, True, True),
        (3, 10, NOW + timedelta(hours=1), 8, 1, 3, 2, 0, True, True),
        (3, 10, NOW, 0, 0, 3, 0, 0, True, True),
        (3, 10, NOW - timedelta(hours=1), 0, 0, 3, 0, 0, True, True),
        (0, 0, NOW - timedelta(days=1), 0, 0, 0, 0, 0, False, False),
        (20, 10, datetime(2026, 11, 16, tzinfo=UTC), 3, 2, 10, 17, 0, True, True),
        (20, 10, datetime(2026, 11, 16, 0, 1, tzinfo=UTC), 3, 3, 10, 27, 0, False, True),
        # A local midnight is the stored instant, not an extra UTC study date.
        (
            20,
            10,
            datetime(2026, 11, 16, tzinfo=timezone(timedelta(hours=8))),
            3,
            2,
            10,
            17,
            0,
            True,
            True,
        ),
        # The buffer instant is today and must use today's spent allowance.
        (20, 10, NOW + timedelta(days=7, hours=1), 8, 8, 10, 72, 2, False, True),
        (20, 10, datetime(2026, 11, 22, tzinfo=UTC), 3, 8, 10, 77, 7, False, True),
    ],
)
def test_exact_exam_utc_windows_and_capacity(
    remaining: int,
    daily: int,
    exam: datetime,
    done: int,
    days: int,
    suggestion: int,
    capacity: int,
    buffer: int,
    impossible: bool,
    risk: bool,
) -> None:
    result = exam_pacing(ProjectPlan(daily_new=daily, exam_date=exam), remaining, done, NOW)
    assert result is not None
    assert result.model_dump() == {
        "remaining_new": remaining,
        "days_left": days,
        "suggested_daily_new": suggestion,
        "capacity": capacity,
        "buffer_capacity": buffer,
        "impossible": impossible,
        "buffer_at_risk": risk,
    }


def test_no_exam_and_new_queue_read_does_not_introduce() -> None:
    assert exam_pacing(ProjectPlan(), 20, 0, NOW) is None
    cards = [card("z", introduced=False), card("a", introduced=False)]
    items = queue(cards, ProjectPlan(daily_new=1), CompletedCounts(), NOW)
    assert [item.memory.id for item in items] == ["z"]
    assert not any(memory.introduced for memory in cards)
    assert items[0].model_dump()["memory_version"] == cards[0].version
    assert queue(cards, ProjectPlan(daily_new=0), CompletedCounts(), NOW) == []
    assert queue(cards, ProjectPlan(daily_new=1), CompletedCounts(new=1), NOW) == []


def test_due_retrievability_due_id_fallback_and_caps() -> None:
    cards = [
        card("stable", stability=100),
        card("forgotten", stability=1),
        card("fallback-z", stability=None),
        card("fallback-a", stability=None),
        card("overdue", stability=None, due=NOW - timedelta(days=1)),
        card("future", due=NOW + timedelta(seconds=1)),
        card("new", introduced=False),
    ]
    result = queue(cards, ProjectPlan(), CompletedCounts(), NOW)
    assert [item.memory.id for item in result] == [
        "overdue",
        "fallback-a",
        "fallback-z",
        "forgotten",
        "stable",
        "new",
    ]
    assert result[0].retrievability is None
    assert queue(cards, ProjectPlan(daily_new=0, review_cap=0), CompletedCounts(), NOW) == []
    assert [
        item.memory.id
        for item in queue(
            cards,
            ProjectPlan(daily_new=1, review_cap=2),
            CompletedCounts(reviews=1),
            NOW,
        )
    ] == ["overdue", "new"]
    invalid = card("invalid", stability=0)
    assert queue([invalid], ProjectPlan(), CompletedCounts(), NOW)[0].retrievability is None


def test_forecast_actual_cards_seven_utc_dates_no_simulation() -> None:
    result = forecast(
        [
            card("overdue", due=NOW - timedelta(days=3)),
            card("today"),
            card("tomorrow", due=NOW + timedelta(days=1)),
            card("last", due=NOW + timedelta(days=6)),
            card("outside", due=NOW + timedelta(days=7)),
            card("unintroduced", introduced=False),
        ],
        NOW,
    )
    assert [day.due for day in result] == [2, 1, 0, 0, 0, 0, 1]
    assert [day.date for day in result] == [NOW.date() + timedelta(days=i) for i in range(7)]


@pytest.mark.parametrize(
    ("offsets", "expected"),
    [([], 0), ([0, 1, 2, 4], 3), ([1, 2, 3], 3), ([2, 3], 0)],
)
def test_streak_today_yesterday_or_broken(offsets: list[int], expected: int) -> None:
    logs = [{"at": NOW - timedelta(days=n), "correct": True} for n in offsets]
    assert history_statistics(logs, NOW)[1] == expected


def test_retention_last_30_utc_dates_and_no_data() -> None:
    assert history_statistics([], NOW) == (None, 0)
    assert (
        history_statistics(
            [{"at": NOW - timedelta(days=30), "correct": False}],
            NOW,
        )[0]
        is None
    )
    logs = [
        {"at": NOW, "correct": True},
        {"at": NOW - timedelta(days=29), "correct": False},
        {"at": NOW - timedelta(days=30), "correct": False},
        {"at": NOW.replace(hour=0) - timedelta(seconds=1), "correct": True},
    ]
    assert history_statistics(logs, NOW)[0] == 2 / 3
    # The previous UTC date must not shift to today's date in an offset timezone.
    logs[-1]["at"] = logs[-1]["at"].astimezone(timezone(timedelta(hours=8)))
    assert history_statistics(logs, NOW) == (2 / 3, 2)


def test_completed_counts_distinguish_introduction_and_later_project() -> None:
    from app.services.study_plan_calculations import completed_counts

    one, two = RecordID("project", "one"), RecordID("project", "two")
    logs = [
        {"at": NOW, "project": one, "is_introduction": True},
        {"at": NOW, "project": two, "is_introduction": False},
        {"at": NOW - timedelta(days=1), "project": two, "is_introduction": True},
    ]
    assert completed_counts(logs, NOW, encode_rid(one, "project")) == CompletedCounts(new=1)
    assert completed_counts(logs, NOW, encode_rid(two, "project")) == CompletedCounts(reviews=1)


def test_dashboard_shared_new_counts_use_available_project_capacity_once() -> None:
    shared, extra = card("shared", introduced=False), card("extra", introduced=False)
    assert available_new_count([([shared, extra], 1), ([shared], 1)]) == 2
    assert available_new_count([([shared], 1), ([shared], 1)]) == 1
    assert available_new_count([([shared, extra], 0), ([shared], 1)]) == 1
    assert available_new_count([([shared], 0)]) == 0
