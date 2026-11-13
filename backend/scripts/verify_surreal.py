"""Regression entrypoint; see docs/dev/surrealdb-notes.md for invocation."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.db.spike import verify

    asyncio.run(verify())


if __name__ == "__main__":
    main()
