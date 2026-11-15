"""Validated optimizer contracts and the pinned scheduler's parameter bounds."""

import math
from datetime import datetime
from importlib.metadata import version
from typing import Literal

from fsrs.scheduler import LOWER_BOUNDS_PARAMETERS, UPPER_BOUNDS_PARAMETERS
from pydantic import BaseModel, ConfigDict

FSRS_VERSION = version("fsrs")
OPTIMIZER_VERSION = f"py-fsrs/{FSRS_VERSION}:pandawords-v1"
MAX_CARDS = 64
MAX_REVIEWS_PER_CARD = 64
MAX_FETCHED_LOGS = MAX_CARDS * (MAX_REVIEWS_PER_CARD + 1)
MAX_LOGS = 1024
# py-fsrs 6.3.3 returns its defaults below its 512-transition mini-batch.
MIN_TRANSITIONS = 512
MIN_CARDS = 10
MIN_NEW_TRANSITIONS = 100
OPTIMIZER_TIMEOUT_SECONDS = 240


class OptimizationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[
        "not_run", "running", "unavailable", "insufficient_history", "failed", "success"
    ] = "not_run"
    reason: str | None = None
    optimizer_version: str = OPTIMIZER_VERSION
    at: datetime | None = None
    eligible_reviews: int = 0
    excluded_reviews: int = 0
    history_fingerprint: str | None = None


def validated_parameters(value: object) -> list[float]:
    if not isinstance(value, list) or len(value) != len(LOWER_BOUNDS_PARAMETERS):
        raise ValueError("Invalid FSRS parameter count")
    result: list[float] = []
    for item, lower, upper in zip(
        value, LOWER_BOUNDS_PARAMETERS, UPPER_BOUNDS_PARAMETERS, strict=True
    ):
        if (
            isinstance(item, bool)
            or not isinstance(item, int | float)
            or not math.isfinite(item)
            or not lower <= item <= upper
        ):
            raise ValueError("Invalid FSRS parameter value")
        result.append(float(item))
    return result
