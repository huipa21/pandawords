import gzip
import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

# isort: split
# Script imports need the same grouping from the repository and backend lint roots.
from scripts.download_lexicon import DownloadError, default_raw_dir, download
from scripts.lexicon_sources import SOURCES

PAYLOADS = {
    "kaikki": b'{"word":"word","pos":"noun","lang_code":"en","senses":[{"glosses":["unit"]}]}\n',
    "ecdict": b"word,translation,pos,tag,exchange,bnc,frq\nword,zi,n,cet4,,1,2\n",
    "oewn": gzip.compress(
        b'<LexicalResource><Lexicon language="en"><LexicalEntry id="word-n"/>'
        b'<Synset id="test-n"/></Lexicon></LexicalResource>'
    ),
}


def contents(path: Path) -> list[Path]:
    return list(path.iterdir())


@pytest.mark.parametrize("name", SOURCES)
async def test_download_each_source_and_verify_cached_file(name: str, tmp_path: Path) -> None:
    source = replace(SOURCES[name], sha256=None)
    payload = PAYLOADS[name]
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=payload, headers={"etag": '"version"'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        record = await download(source, tmp_path, client, fallback_url="https://mirror.test/data")
        cached = await download(source, tmp_path, client)
    assert calls == [source.url]
    assert (tmp_path / source.filename).read_bytes() == payload
    assert cached == record
    assert record["sha256"] == hashlib.sha256(payload).hexdigest()
    assert record["license"] == source.license
    assert record["retrieved_at"]
    assert record["version"] == source.version
    assert json.loads((tmp_path / "manifest.json").read_text())["artifacts"][name] == record
    assert sorted(p.name for p in contents(tmp_path)) == [source.filename, "manifest.json"]


@pytest.mark.parametrize("failure", ["http", "network", "format", "length"])
async def test_fallback_only_after_official_failure(failure: str, tmp_path: Path) -> None:
    source = SOURCES["kaikki"]
    calls: list[str] = []
    mirror = "https://mirror.test/kaikki"

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == source.url:
            if failure == "network":
                raise httpx.ConnectError("unreachable", request=request)
            if failure == "http":
                return httpx.Response(503)
            if failure == "length":
                return httpx.Response(
                    200, content=PAYLOADS["kaikki"], headers={"content-length": "1"}
                )
            return httpx.Response(200, content=b"<html>not a dictionary</html>")
        return httpx.Response(200, content=PAYLOADS["kaikki"])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        record = await download(source, tmp_path, client, fallback_url=mirror)
    assert calls == [source.url, mirror]
    assert record["origin"] == "fallback"
    assert record["url"] == mirror
    assert record["official_url"] == source.url


@pytest.mark.parametrize("name", SOURCES)
async def test_failure_cleans_partials_and_identifies_source(name: str, tmp_path: Path) -> None:
    source = replace(SOURCES[name], sha256=None)
    payload = PAYLOADS[name][:-8]

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    ) as client:
        with pytest.raises(DownloadError, match=name):
            await download(source, tmp_path, client, fallback_url="https://mirror.test/data")
    assert contents(tmp_path) == []


@pytest.mark.parametrize("change", ["tampered", "untracked", "new_upstream", "pin"])
async def test_integrity_mismatches_never_overwrite(change: str, tmp_path: Path) -> None:
    source = SOURCES["kaikki"]
    payload = PAYLOADS["kaikki"]
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        await download(source, tmp_path, client)
        manifest_path = tmp_path / "manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        target = tmp_path / source.filename
        if change == "tampered":
            target.write_bytes(b"corrupted")
        elif change == "untracked":
            manifest_path.unlink()
        elif change == "new_upstream":
            target.unlink()
            payload = PAYLOADS["kaikki"].replace(b"word", b"term")
        before = target.read_bytes() if target.exists() else None
        with pytest.raises(DownloadError, match="kaikki:.*(checksum|manifest|SHA-256)"):
            await download(
                source,
                tmp_path,
                client,
                expected_sha256="0" * 64 if change == "pin" else None,
            )
        assert (target.read_bytes() if target.exists() else None) == before
        if change != "untracked":
            assert manifest_path.read_bytes() == manifest_bytes
    assert len(calls) == (2 if change == "new_upstream" else 1)
    assert not [path for path in contents(tmp_path) if path.name.startswith(".")]


async def test_sources_preserve_each_others_manifest_records(tmp_path: Path) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=PAYLOADS["ecdict" if "ecdict" in str(request.url) else "kaikki"]
            )
        )
    ) as client:
        first = await download(SOURCES["kaikki"], tmp_path, client)
        await download(SOURCES["ecdict"], tmp_path, client)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert set(manifest["artifacts"]) == {"kaikki", "ecdict"}
    assert manifest["artifacts"]["kaikki"] == first


async def test_manifest_publish_failure_removes_unrecorded_download(tmp_path: Path) -> None:
    source = SOURCES["kaikki"]
    original = Path.replace

    def fail_manifest(path: Path, target: Path) -> Path:
        if target.name == "manifest.json":
            raise PermissionError("cannot publish manifest")
        return original(path, target)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=PAYLOADS["kaikki"]))
    ) as client:
        with patch.object(Path, "replace", fail_manifest):
            with pytest.raises(DownloadError, match="kaikki: cannot publish manifest"):
                await download(source, tmp_path, client)
    assert contents(tmp_path) == []


async def test_lock_refuses_concurrent_writes_without_removing_owner_lock(tmp_path: Path) -> None:
    lock = tmp_path / ".download.lock"
    lock.touch()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail())) as client:
        with pytest.raises(DownloadError, match="kaikki: another download"):
            await download(SOURCES["kaikki"], tmp_path, client)
    assert lock.exists()


def test_default_data_directory_is_shared_by_worktrees(tmp_path: Path) -> None:
    with patch(
        "scripts.download_lexicon.subprocess.check_output", return_value=str(tmp_path / ".git")
    ):
        assert default_raw_dir() == tmp_path / "data" / "lexicon" / "raw"


@pytest.mark.parametrize("manifest", ['{"schema_version":2}', "{broken", '{"artifacts":null}'])
async def test_bad_manifest_never_starts_a_download(manifest: str, tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(manifest)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail())) as client:
        with pytest.raises(DownloadError, match="kaikki:"):
            await download(SOURCES["kaikki"], tmp_path, client)
    assert path.read_text() == manifest
    assert contents(tmp_path) == [path]


async def test_stream_interruption_never_publishes_partial_file(tmp_path: Path) -> None:
    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield PAYLOADS["kaikki"]
            raise httpx.ReadError("connection dropped")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=BrokenStream()))
    ) as client:
        with pytest.raises(DownloadError, match="kaikki:.*connection dropped"):
            await download(SOURCES["kaikki"], tmp_path, client)
    assert contents(tmp_path) == []
