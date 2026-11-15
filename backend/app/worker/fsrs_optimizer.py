"""Disposable bounded CPU process; optional optimizer imports never enter the API."""

import json
import sys

from fsrs import Rating, ReviewLog

from app.domain.srs_optimization import MAX_LOGS, validated_parameters


def main() -> None:
    try:
        from fsrs import Optimizer
        from torch import set_num_threads
    except ImportError, OSError:
        print(json.dumps({"status": "unavailable"}))
        return
    from datetime import datetime

    try:
        raw = json.loads(sys.stdin.buffer.read(2_000_000))
        if not isinstance(raw, list) or len(raw) > MAX_LOGS:
            raise ValueError("History limit")
        set_num_threads(1)
        logs = [
            ReviewLog(
                card_id=row["card_id"],
                rating=Rating(row["rating"]),
                review_datetime=datetime.fromisoformat(row["review_datetime"]),
                review_duration=row["review_duration"],
            )
            for row in raw
        ]
        try:
            optimizer = Optimizer(logs)
        except ImportError, OSError:
            print(json.dumps({"status": "unavailable"}))
            return
        values = validated_parameters(optimizer.compute_optimal_parameters())
        print(json.dumps({"status": "success", "parameters": values}, allow_nan=False))
    except Exception:
        print(json.dumps({"status": "failed"}))


if __name__ == "__main__":
    main()
