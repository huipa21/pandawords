import gzip
import json
import sqlite3
import tarfile
from contextlib import closing
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

# isort: split
from scripts import lexicon_release

# isort: split
from scripts.build_lexicon import main as build_main
from scripts.download_lexicon import checksum
from scripts.lexicon_sources import SOURCES

DAY = date(2026, 11, 14)


def sources(raw: Path) -> dict[str, Any]:
    raw.mkdir(parents=True)
    entries = [
        {
            "word": word,
            "lang_code": "en",
            "pos": "adj",
            "senses": [{"glosses": ["giving much light"]}],
        }
        for word in ("bright", "luminous")
    ]
    (raw / SOURCES["kaikki"].filename).write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8"
    )
    (raw / SOURCES["ecdict"].filename).write_text(
        "word,translation,pos,tag,exchange,bnc,frq\nbright,a. 明亮的,a,cet4,,1,2\n",
        encoding="utf-8",
    )
    xml = Path(__file__).parents[1] / "fixtures" / "oewn-small.xml"
    (raw / SOURCES["oewn"].filename).write_bytes(gzip.compress(xml.read_bytes(), mtime=0))
    records = {}
    for key, source in SOURCES.items():
        path = raw / source.filename
        records[key] = {
            "filename": source.filename,
            "sha256": checksum(path),
            "bytes": path.stat().st_size,
            "retrieved_at": "2026-11-14T00:00:00Z",
            "url": source.url,
            "license": source.license,
            "version": source.version,
        }
    manifest = {"schema_version": 1, "artifacts": records}
    (raw / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


@pytest.fixture
def staged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, dict[str, Any]]:
    raw = tmp_path / "data" / "raw"
    manifest = sources(raw)
    # Only the synthetic fixture has a different release pin; production keeps the official pin.
    monkeypatch.setitem(
        SOURCES, "oewn", replace(SOURCES["oewn"], sha256=manifest["artifacts"]["oewn"]["sha256"])
    )
    native_client = httpx.AsyncClient

    def deny(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"offline test attempted network: {request.url}")

    monkeypatch.setattr(
        lexicon_release.httpx,
        "AsyncClient",
        lambda **kwargs: native_client(transport=httpx.MockTransport(deny), **kwargs),
    )
    return raw, tmp_path / "data" / "lexicon.sqlite", tmp_path / "dist", manifest


def verify_archive(archive: Path, unpacked: Path) -> dict[str, Any]:
    with tarfile.open(archive, "r:gz") as bundle:
        assert sorted(bundle.getnames()) == ["SHA256SUMS", "lexicon.sqlite", "manifest.json"]
        bundle.extractall(unpacked, filter="data")
    for line in (unpacked / "SHA256SUMS").read_text().splitlines():
        digest, filename = line.split("  ")
        assert checksum(unpacked / filename) == digest
    digest, filename = archive.with_name(archive.name + ".sha256").read_text().strip().split("  ")
    assert filename == archive.name
    assert digest == checksum(archive)
    manifest = json.loads((unpacked / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["database"]["sha256"] == checksum(unpacked / "lexicon.sqlite")
    with closing(sqlite3.connect(unpacked / "lexicon.sqlite")) as db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT gloss_zh FROM sense WHERE gloss_zh IS NOT NULL").fetchone()
        assert db.execute("SELECT count(*) FROM freq WHERE source='wordfreq'").fetchone() == (2,)
        assert db.execute("SELECT count(*) FROM relation WHERE type='synonym'").fetchone() == (2,)
        assert db.execute("SELECT count(*) FROM lemma WHERE freq_zipf > 0").fetchone() == (2,)
        assert db.execute("SELECT count(*) FROM sense WHERE common=1").fetchone()[0] > 0
    return manifest


def test_offline_package_contains_combined_enrichment_and_provenance(
    staged: tuple[Path, Path, Path, dict[str, Any]], tmp_path: Path
) -> None:
    raw, output, dist, original = staged
    archive = lexicon_release.release(raw, output, dist, DAY)
    assert archive.name == "pandawords-lexicon-2026-11-14.tar.gz"
    manifest = verify_archive(archive, tmp_path / "unpacked")
    assert manifest["artifacts"] == original["artifacts"]
    assert {"wiktionary", "ecdict", "wordfreq", "oewn", "oewn:approx"} <= manifest["sources"].keys()
    assert checksum(output) == manifest["database"]["sha256"]
    assert not list(output.parent.glob(".lexicon*"))
    assert not list(dist.glob(".lexicon*"))


def test_missing_sources_use_official_verified_downloader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = tmp_path / "seed"
    manifest = sources(seeded)
    payloads = {source.url: (seeded / source.filename).read_bytes() for source in SOURCES.values()}
    monkeypatch.setitem(
        SOURCES, "oewn", replace(SOURCES["oewn"], sha256=manifest["artifacts"]["oewn"]["sha256"])
    )
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=payloads[str(request.url)])

    native_client = httpx.AsyncClient
    monkeypatch.setattr(
        lexicon_release.httpx,
        "AsyncClient",
        lambda **kwargs: native_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    raw = tmp_path / "raw"
    archive = lexicon_release.release(
        raw, tmp_path / "data" / "lexicon.sqlite", tmp_path / "dist", DAY
    )
    assert calls == list(payloads)
    downloaded = json.loads((raw / "manifest.json").read_text())
    assert all(record["origin"] == "official" for record in downloaded["artifacts"].values())
    verify_archive(archive, tmp_path / "unpacked")


@pytest.mark.parametrize("stage", ["download:kaikki", "build", "package", "publish"])
def test_stage_failures_leave_no_partial_artifacts(
    stage: str,
    staged: tuple[Path, Path, Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, output, dist, _ = staged
    if stage == "download:kaikki":
        (raw / SOURCES["kaikki"].filename).write_text("mismatch", encoding="utf-8")
    elif stage == "build":
        monkeypatch.setattr(lexicon_release, "wordfreq_enricher", lambda: 1 / 0)
    elif stage == "package":
        monkeypatch.setattr(lexicon_release.tarfile, "open", lambda *a, **k: 1 / 0)
    else:
        native_publish = lexicon_release.publish

        def fail_archive(source: Path, target: Path) -> None:
            if target.suffix == ".gz":
                raise OSError("synthetic archive publication failure")
            native_publish(source, target)

        monkeypatch.setattr(lexicon_release, "publish", fail_archive)
    before = {path.name: path.read_bytes() for path in raw.iterdir()}
    with pytest.raises(lexicon_release.ReleaseError, match=f"lexicon {stage} failed:"):
        lexicon_release.release(raw, output, dist, DAY)
    assert not output.exists()
    assert list(dist.iterdir()) == []
    assert not list(output.parent.glob(".lexicon*"))
    assert {path.name: path.read_bytes() for path in raw.iterdir()} == before


def test_never_overwrites_database_or_release_and_keeps_foreign_lock(
    staged: tuple[Path, Path, Path, dict[str, Any]],
) -> None:
    raw, output, dist, _ = staged
    output.write_bytes(b"existing database")
    with pytest.raises(
        lexicon_release.ReleaseError, match="publish failed: existing database differs"
    ):
        lexicon_release.release(raw, output, dist, DAY)
    assert output.read_bytes() == b"existing database"
    assert list(dist.iterdir()) == []
    output.unlink()
    archive = lexicon_release.release(raw, output, dist, DAY)
    before = {path.name: checksum(path) for path in dist.iterdir()}
    with pytest.raises(lexicon_release.ReleaseError, match="prepare failed: output already exists"):
        lexicon_release.release(raw, output, dist, DAY)
    assert {path.name: checksum(path) for path in dist.iterdir()} == before
    assert archive.exists()
    lock = output.parent / ".lexicon-release.lock"
    lock.touch()
    with pytest.raises(lexicon_release.ReleaseError, match="prepare failed:"):
        lexicon_release.release(raw, output, dist, DAY)
    assert lock.exists()


@pytest.mark.parametrize("stage", ["download:kaikki", "build", "package", "publish"])
def test_cli_nonzero_includes_stage(
    stage: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*args: Any) -> Path:
        raise lexicon_release.ReleaseError(f"lexicon {stage} failed: synthetic")

    monkeypatch.setattr(lexicon_release, "release", fail)
    monkeypatch.setattr(
        "sys.argv",
        [
            "lexicon_release",
            "--raw-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "out.sqlite"),
            "--dist-dir",
            str(tmp_path / "dist"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        lexicon_release.main()
    assert error.value.code == 1
    assert f"lexicon {stage} failed: synthetic" in capsys.readouterr().err


def test_builder_cli_enables_oewn_after_other_hooks(
    staged: tuple[Path, Path, Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, output, _, _ = staged
    arguments = ["build", "--output", str(output), "--wordfreq"]
    for key in ("kaikki", "ecdict", "oewn"):
        arguments += [f"--{key}", str(raw / SOURCES[key].filename)]
    monkeypatch.setattr("sys.argv", arguments)
    build_main()
    with closing(sqlite3.connect(output)) as db:
        assert db.execute("SELECT count(*) FROM relation").fetchone() == (2,)
        assert db.execute("SELECT count(*) FROM freq WHERE source='wordfreq'").fetchone() == (2,)
        assert db.execute("SELECT count(*) FROM zh_gloss").fetchone() == (1,)
    before = output.read_bytes()
    (raw / SOURCES["oewn"].filename).write_bytes(b"invalid gzip")
    with pytest.raises(SystemExit) as error:
        build_main()
    assert error.value.code == 1
    assert output.read_bytes() == before
