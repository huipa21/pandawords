import asyncio
import io
import json
import sys
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import fsrs
import pytest
from fsrs.scheduler import DEFAULT_PARAMETERS

from app.domain.identity import user_subject
from app.domain.srs_optimization import MAX_LOGS, MIN_TRANSITIONS, validated_parameters
from app.services import srs_optimization
from app.services.srs_optimization_history import eligible_transitions, training_history
from app.worker import fsrs_optimizer
from tests.srs_optimization_support import history

OWNER = user_subject("optimizer_unit")


def test_pinned_optimizer_eligibility_counts_only_non_same_day_transitions() -> None:
    now = datetime.now(UTC)
    rows = history(OWNER, cards=16, reviews=33)
    logs, excluded = training_history(rows, OWNER, now)
    assert excluded == 0
    assert eligible_transitions(logs) == (MIN_TRANSITIONS, 16)
    assert eligible_transitions(training_history(rows[:-1], OWNER, now)[0]) == (511, 16)
    short = history(OWNER, cards=1, reviews=3, interval=timedelta(hours=23))
    assert eligible_transitions(training_history(short, OWNER, now)[0]) == (0, 0)
    long = history(OWNER, cards=1, reviews=3, interval=timedelta(days=1))
    assert eligible_transitions(training_history(long, OWNER, now)[0]) == (2, 1)


def test_training_rejects_foreign_incomplete_malformed_and_outlier_sequences() -> None:
    now = datetime.now(UTC)
    rows = history(OWNER, cards=1, reviews=11)
    foreign = history(user_subject("other"), cards=1, reviews=11)
    logs, excluded = training_history([*rows, *foreign], OWNER, now)
    assert eligible_transitions(logs) == (10, 1)
    assert excluded == len(foreign)
    assert training_history(rows[1:], OWNER, now) == ([], 10)
    assert training_history([rows[0], rows[0], rows[1]], OWNER, now) == ([], 3)

    for field, value in (
        ("receipt", {}),
        ("duration_ms", 60001),
        ("at", now + timedelta(days=1)),
        ("request_fingerprint", "not-a-server-fingerprint"),
        ("correct", not rows[5]["correct"]),
    ):
        damaged = deepcopy(rows)
        damaged[5][field] = value
        # A broken interior review must not turn the remaining rows into a false sequence.
        assert training_history(damaged, OWNER, now) == ([], len(damaged))

    boundary = deepcopy(rows)
    boundary[0]["duration_ms"] = 0
    boundary[1]["duration_ms"] = 60000
    assert training_history(boundary, OWNER, now)[1] == 0


def test_adjusted_review_time_and_bounded_deterministic_sample() -> None:
    now = datetime.now(UTC)
    rows = history(OWNER, cards=1, reviews=2)
    rows[1]["at"] = rows[0]["at"]
    rows[1]["receipt"]["at"] = rows[0]["at"].isoformat()
    adjusted = rows[0]["at"] + timedelta(microseconds=1)
    rows[1]["receipt"]["memory"]["card"]["last_review"] = adjusted.isoformat()
    logs, excluded = training_history(rows, OWNER, now)
    assert excluded == 0 and len(logs) == 2
    assert datetime.fromisoformat(logs[1]["review_datetime"]) == adjusted

    rows = history(OWNER, cards=40, reviews=40)
    logs, excluded = training_history(rows, OWNER, now)
    assert len(logs) == MAX_LOGS and excluded == len(rows) - MAX_LOGS
    counts = Counter(log["card_id"] for log in logs)
    assert len(counts) == 40 and min(counts.values()) >= 2 and max(counts.values()) == 40
    assert training_history(list(reversed(rows)), OWNER, now) == (logs, excluded)
    capped, skipped = training_history(history(OWNER, cards=1, reviews=70), OWNER, now)
    assert len(capped) == 64 and skipped == 6


def test_recent_usable_reviews_enter_a_full_training_sample() -> None:
    now = datetime.now(UTC)
    rows = history(
        OWNER, cards=40, reviews=41, start=now - timedelta(days=40), interval=timedelta(days=1)
    )
    rows = [
        row
        for row in rows
        if row["at"] < now
        or row["memory"].id[1].id in {f"optimization-{index}" for index in range(10)}
    ]
    logs, _ = training_history(rows, OWNER, now)
    assert len(logs) == MAX_LOGS
    assert eligible_transitions(logs, since=now - timedelta(days=1))[0] == 10


def test_truncated_card_uses_a_contiguous_recent_window() -> None:
    now = datetime.now(UTC)
    rows = history(OWNER, cards=1, reviews=70)
    logs, excluded = training_history(rows[-65:], OWNER, now)
    assert excluded == 1 and len(logs) == 64
    assert datetime.fromisoformat(logs[0]["review_datetime"]) == rows[6]["at"]
    assert datetime.fromisoformat(logs[-1]["review_datetime"]) == rows[-1]["at"]
    assert eligible_transitions(logs) == (63, 1)
    assert training_history(rows[-64:], OWNER, now) == ([], 64)


@pytest.mark.parametrize(
    "values",
    [[], [True] * 21, [float("nan")] * 21, [float("inf")] * 21, [-1.0] * 21, [101.0] * 21],
)
def test_optimizer_output_must_match_pinned_bounds(values: list) -> None:
    with pytest.raises(ValueError):
        validated_parameters(values)


async def test_real_supported_optimizer_or_explicit_optional_unavailable() -> None:
    logs, _ = training_history(history(OWNER, cards=16, reviews=33), OWNER, datetime.now(UTC))
    assert eligible_transitions(logs) == (512, 16)
    status, values = await srs_optimization.compute(logs)
    assert status in {"success", "unavailable"}
    if status == "success":
        assert tuple(validated_parameters(values)) != DEFAULT_PARAMETERS


def test_upstream_stub_without_optimizer_dependencies_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class MissingOptimizer:
        def __init__(self, *_: object) -> None:
            raise ImportError("optional dependencies are absent")

    monkeypatch.setitem(fsrs.__dict__, "Optimizer", MissingOptimizer)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(set_num_threads=lambda _: None))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"[]")))
    fsrs_optimizer.main()
    assert json.loads(capsys.readouterr().out) == {"status": "unavailable"}


def test_missing_torch_is_unavailable_without_affecting_scheduler(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(fsrs.__dict__, "Optimizer", object)
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"[]")))
    fsrs_optimizer.main()
    assert json.loads(capsys.readouterr().out) == {"status": "unavailable"}
    assert tuple(fsrs.Scheduler().parameters) == DEFAULT_PARAMETERS


@pytest.mark.parametrize("outcome", ["timeout", "cancelled"])
async def test_interruption_kills_and_reaps_only_owned_child(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    started = asyncio.Event()

    class Process:
        returncode = None
        killed = False
        waited = False

        async def communicate(self, _: bytes) -> tuple[bytes, bytes]:
            if outcome == "timeout":
                raise TimeoutError
            started.set()
            await asyncio.Event().wait()
            return b"", b""

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            self.waited = True
            return 0

    process = Process()

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    if outcome == "timeout":
        with pytest.raises(TimeoutError):
            await srs_optimization.compute([])
    else:
        task = asyncio.create_task(srs_optimization.compute([]))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert process.killed and process.waited
