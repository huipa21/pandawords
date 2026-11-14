"""Rebuild the committed synthetic fixture through the production pipeline, offline."""

import argparse
import json
from pathlib import Path

from .build_lexicon import BuildResult, build
from .lexicon_ecdict import ecdict_enricher
from .lexicon_frequency import wordfreq_enricher
from .lexicon_oewn import oewn_enricher

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def build_fixture(output: Path = FIXTURES / "lexicon_small.sqlite") -> BuildResult:
    words = set((FIXTURES / "lexicon-small.words").read_text(encoding="utf-8").splitlines())
    frequencies: dict[str, float] = json.loads(
        (FIXTURES / "lexicon-small-frequency.json").read_text(encoding="utf-8")
    )
    return build(
        FIXTURES / "lexicon-small.jsonl",
        output,
        words=words,
        enrichers=(
            ecdict_enricher(FIXTURES / "lexicon-small-ecdict.csv"),
            wordfreq_enricher(
                lookup=frequencies.__getitem__, package_version="synthetic-fixture-v1"
            ),
            oewn_enricher(FIXTURES / "lexicon-small-oewn.xml"),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FIXTURES / "lexicon_small.sqlite")
    arguments = parser.parse_args()
    result = build_fixture(arguments.output)
    print(f"Built {result.records} records; skipped {result.skipped_senses} unusable senses.")


if __name__ == "__main__":
    main()
