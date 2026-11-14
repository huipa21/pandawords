"""Download, build and package a lexicon: python -m scripts.lexicon_release."""

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from .build_lexicon import build
from .download_lexicon import checksum, default_raw_dir, download
from .lexicon_ecdict import ecdict_enricher
from .lexicon_frequency import wordfreq_enricher
from .lexicon_oewn import oewn_enricher
from .lexicon_schema import SCHEMA_VERSION
from .lexicon_sources import SOURCES


class ReleaseError(Exception):
    """A release failure with its explicit stage."""


def publish(source: Path, target: Path) -> None:
    """Publish complete bytes exclusively, without replacing an existing target."""
    os.link(source, target)


async def download_sources(raw: Path) -> dict[str, Any]:
    records = {}
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        for key, source in SOURCES.items():
            try:
                records[key] = await download(source, raw, client)
            except Exception as error:
                raise ReleaseError(f"lexicon download:{key} failed: {error}") from error
    return records


def release(raw: Path, output: Path, dist: Path, day: date) -> Path:
    stage_name = "prepare"
    lock: Path | None = None
    stage: Path | None = None
    archive_stage: Path | None = None
    published: list[Path] = []
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        candidate = output.parent / ".lexicon-release.lock"
        candidate.touch(exist_ok=False)
        lock = candidate
        dist.mkdir(parents=True, exist_ok=True)
        name = f"pandawords-lexicon-{day.isoformat()}.tar.gz"
        archive = dist / name
        sidecar = dist / f"{name}.sha256"
        for path in (archive, sidecar):
            if path.exists():
                raise ValueError(f"output already exists: {path}; choose another date/directory")
        token = uuid4().hex
        stage = output.parent / f".lexicon-{token}"
        stage.mkdir()
        archive_stage = dist / f".lexicon-{token}"
        archive_stage.mkdir()
        stage_name = "download"
        records = asyncio.run(download_sources(raw))
        stage_name = "build"
        database = stage / "lexicon.sqlite"
        result = build(
            raw / SOURCES["kaikki"].filename,
            database,
            enrichers=(
                ecdict_enricher(raw / SOURCES["ecdict"].filename),
                wordfreq_enricher(),
                oewn_enricher(raw / SOURCES["oewn"].filename),
            ),
        )
        stage_name = "package"
        with closing(sqlite3.connect(database)) as connection:
            sources = {
                name: json.loads(metadata)
                for name, metadata in connection.execute("SELECT name, metadata FROM source")
            }
        manifest = stage / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "release_date": day.isoformat(),
                    "artifacts": records,
                    "database": {
                        "filename": database.name,
                        "schema_version": SCHEMA_VERSION,
                        "sha256": checksum(database),
                        "bytes": database.stat().st_size,
                        "records": result.records,
                        "skipped_senses": result.skipped_senses,
                    },
                    "sources": sources,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        sums = stage / "SHA256SUMS"
        sums.write_text(
            "".join(f"{checksum(path)}  {path.name}\n" for path in (database, manifest)),
            encoding="utf-8",
        )
        packed = archive_stage / name
        with tarfile.open(packed, "w:gz") as bundle:
            for path in (database, manifest, sums):
                bundle.add(path, arcname=path.name, recursive=False)
        packed_sum = archive_stage / sidecar.name
        packed_sum.write_text(f"{checksum(packed)}  {name}\n", encoding="utf-8")
        stage_name = "publish"
        # The archive is the completion marker. Roll back only paths created by this run.
        if output.exists():
            if checksum(output) != checksum(database):
                raise ValueError(
                    f"existing database differs: {output}; choose another --output or move it first"
                )
        else:
            publish(database, output)
            published.append(output)
        publish(packed_sum, sidecar)
        published.append(sidecar)
        publish(packed, archive)
        published.append(archive)
        return archive
    except Exception as error:
        for path in reversed(published):
            path.unlink()
        if isinstance(error, ReleaseError):
            raise
        raise ReleaseError(f"lexicon {stage_name} failed: {error}") from error
    finally:
        for directory in (stage, archive_stage):
            if directory is not None:
                shutil.rmtree(directory)
        if lock is not None:
            lock.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, help="default: main worktree data/lexicon/raw")
    parser.add_argument(
        "--output", type=Path, help="default: main worktree data/lexicon/lexicon.sqlite"
    )
    parser.add_argument("--dist-dir", type=Path, help="default: main worktree dist")
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(UTC).date())
    args = parser.parse_args()
    try:
        root = (
            default_raw_dir().parents[2]
            if any(path is None for path in (args.raw_dir, args.output, args.dist_dir))
            else Path()
        )
        archive = release(
            args.raw_dir if args.raw_dir is not None else root / "data" / "lexicon" / "raw",
            args.output
            if args.output is not None
            else root / "data" / "lexicon" / "lexicon.sqlite",
            args.dist_dir if args.dist_dir is not None else root / "dist",
            args.date,
        )
    except ReleaseError as error:
        parser.exit(1, f"{error}\n")
    except (OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"lexicon prepare failed: {error}\n")
    print(f"Lexicon release: {archive}")


if __name__ == "__main__":
    main()
