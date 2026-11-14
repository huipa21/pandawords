"""Download one lexicon source; run from backend with python -m scripts.download_lexicon."""

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from .lexicon_sources import SOURCES, Source, validate_payload


class DownloadError(Exception):
    """A source-specific download or integrity failure."""


def default_raw_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    common = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=root,
        text=True,
    ).strip()
    return Path(common).parent / "data" / "lexicon" / "raw"


def checksum(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "artifacts": {}}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or not isinstance(manifest.get("artifacts"), dict)
    ):
        raise ValueError("invalid manifest schema")
    return manifest


def checked_record(manifest: dict[str, Any], source: Source) -> dict[str, Any] | None:
    record = manifest["artifacts"].get(source.name)
    if record is None and source.name not in manifest["artifacts"]:
        return None
    if (
        not isinstance(record, dict)
        or record.get("filename") != source.filename
        or not isinstance(record.get("sha256"), str)
        or re.fullmatch(r"[a-f0-9]{64}", record["sha256"]) is None
        or not isinstance(record.get("bytes"), int)
        or record["bytes"] <= 0
        or not record.get("retrieved_at")
        or not record.get("license")
        or not record.get("url")
    ):
        raise ValueError(f"invalid manifest record for {source.name}")
    return record


def validate_url(url: str) -> None:
    parsed = httpx.URL(url)
    if parsed.scheme != "https" or not parsed.host or parsed.userinfo:
        raise ValueError("source URLs must be HTTPS without credentials")


async def fetch(
    client: httpx.AsyncClient, source: Source, url: str, stage: Path, expected: str | None
) -> dict[str, Any]:
    validate_url(url)
    digest = hashlib.sha256()
    size = 0
    async with client.stream("GET", url, headers={"Accept-Encoding": "identity"}) as response:
        response.raise_for_status()
        validate_url(str(response.url))
        if response.headers.get("content-encoding", "identity") != "identity":
            raise ValueError("unexpected HTTP content encoding")
        with stage.open("xb") as file:
            async for chunk in response.aiter_bytes(1024 * 1024):
                file.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if "content-length" in response.headers and size != int(response.headers["content-length"]):
            raise ValueError("incomplete response (Content-Length mismatch)")
        actual = digest.hexdigest()
        if expected is not None and actual != expected:
            raise ValueError(f"SHA-256 mismatch: expected {expected}, received {actual}")
        await asyncio.to_thread(validate_payload, source, stage)
        return {
            "filename": source.filename,
            "official_url": source.url,
            "url": url,
            "resolved_url": str(response.url),
            "origin": "official" if url == source.url else "fallback",
            "version": source.version,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "license": source.license,
            "license_url": source.license_url,
            "sha256": actual,
            "bytes": size,
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
        }


async def download(
    source: Source,
    raw_dir: Path,
    client: httpx.AsyncClient,
    *,
    fallback_url: str | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Verify cached bytes, or atomically fetch and record a single source."""
    lock = raw_dir / ".download.lock"
    try:
        await asyncio.to_thread(raw_dir.mkdir, parents=True, exist_ok=True)
        lock.touch(exist_ok=False)
    except FileExistsError as error:
        raise DownloadError(f"{source.name}: another download holds {lock}") from error
    except OSError as error:
        raise DownloadError(f"{source.name}: {error}") from error
    token = uuid4().hex
    stage = raw_dir / f".{source.filename}.{token}.part"
    manifest_stage = raw_dir / f".manifest.{token}.part"
    target = raw_dir / source.filename
    try:
        if expected_sha256 is not None and re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None:
            raise ValueError("--sha256 must contain 64 lowercase hexadecimal characters")
        manifest_path = raw_dir / "manifest.json"
        manifest = await asyncio.to_thread(read_manifest, manifest_path)
        previous = checked_record(manifest, source)
        pins = {pin for pin in (source.sha256, expected_sha256) if pin is not None}
        if previous is not None:
            pins.add(previous["sha256"])
        if len(pins) > 1:
            raise ValueError("checksum pins disagree with the manifest or official release")
        expected = next(iter(pins), None)
        if target.exists():
            if previous is None:
                raise ValueError("existing file has no manifest record; refusing to overwrite")
            if (
                target.stat().st_size != previous["bytes"]
                or await asyncio.to_thread(checksum, target) != expected
            ):
                raise ValueError("existing file disagrees with manifest; refusing to overwrite")
            return previous
        failures: list[str] = []
        record: dict[str, Any] | None = None
        for url in (source.url, fallback_url):
            if url is None:
                continue
            try:
                record = await fetch(client, source, url, stage, expected)
                break
            except (httpx.HTTPError, ValueError, OSError, EOFError) as error:
                failures.append(f"{url}: {error}")
                stage.unlink(missing_ok=True)
        if record is None:
            raise ValueError("; ".join(failures))
        if previous is not None and record["bytes"] != previous["bytes"]:
            raise ValueError("download size disagrees with manifest")
        manifest["artifacts"][source.name] = record
        manifest_stage.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        stage.replace(target)
        try:
            manifest_stage.replace(manifest_path)
        except OSError:
            target.unlink(missing_ok=True)
            raise
        return record
    except (httpx.HTTPError, ValueError, OSError, EOFError) as error:
        raise DownloadError(f"{source.name}: {error}") from error
    finally:
        stage.unlink(missing_ok=True)
        manifest_stage.unlink(missing_ok=True)
        lock.unlink()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=SOURCES)
    parser.add_argument("--raw-dir", type=Path, help="default: main worktree data/lexicon/raw")
    parser.add_argument("--fallback-url", help="same artifact over HTTPS; only tried after failure")
    parser.add_argument("--sha256", help="optional trusted SHA-256 pin for mutable upstreams")
    args = parser.parse_args()
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
            record = await download(
                SOURCES[args.source],
                args.raw_dir if args.raw_dir is not None else default_raw_dir(),
                client,
                fallback_url=args.fallback_url,
                expected_sha256=args.sha256,
            )
    except (DownloadError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{args.source}: {error}\n")
    print(f"{args.source}: {record['filename']} SHA-256 {record['sha256']}")


if __name__ == "__main__":
    asyncio.run(main())
