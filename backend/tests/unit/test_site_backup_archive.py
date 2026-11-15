from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.backup import __main__ as cli
from app.backup.schedule import next_run
from app.core.config import Settings
from app.domain.site_backup import SiteBackupError
from app.services import site_backup_archive as archive
from app.services.site_backup import check_locations

_DB = b"OPTION IMPORT;\n"


def _manifest(**changes: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "format": "pandawords.site",
        "version": 1,
        "app_version": "test",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "trigger": "manual",
        "lexicon_version": None,
        "source_lang": "zh",
        "target_lang": "en",
        "attribution": [],
        "database": {"size": len(_DB), "sha256": hashlib.sha256(_DB).hexdigest(), "tables": {}},
        "media": [],
    }
    manifest.update(changes)
    return manifest


def _tar(
    path: Path, manifest: dict[str, object], entries: list[tarfile.TarInfo | tuple[str, bytes]]
) -> Path:
    with tarfile.open(path, "w:gz") as output:
        for name, data in [("manifest.json", json.dumps(manifest).encode()), ("db.surql", _DB)]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            output.addfile(info, io.BytesIO(data))
        for entry in entries:
            if isinstance(entry, tarfile.TarInfo):
                output.addfile(entry)
                continue
            info = tarfile.TarInfo(entry[0])
            info.size = len(entry[1])
            output.addfile(info, io.BytesIO(entry[1]))
    return path


def _read(path: Path, destination: Path | None = None) -> None:
    def route(name: str) -> Path:
        assert destination is not None
        return archive.contained(destination, name)

    archive.read_archive(
        path, max_entries=100, max_bytes=10_000, destination=route if destination else None
    )


def _media(name: str, data: bytes) -> dict[str, object]:
    return {"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_valid_archive_round_trips(tmp_path: Path) -> None:
    path = _tar(
        tmp_path / "a.tar.gz",
        _manifest(media=[_media("x/y.bin", b"abc")]),
        [("media/x/y.bin", b"abc")],
    )
    _read(path, tmp_path / "out")
    assert (tmp_path / "out" / "media" / "x" / "y.bin").read_bytes() == b"abc"


@pytest.mark.parametrize(
    ("manifest", "entries", "stage"),
    [
        (_manifest(format="pandawords.user"), [], "manifest"),
        (_manifest(version=2), [], "manifest"),
        (_manifest(media=[_media("../evil", b"x")]), [("media/../evil", b"x")], "manifest"),
        (_manifest(), [("../evil", b"x")], "unsafe_entry"),
        (_manifest(), [("/abs", b"x")], "unsafe_entry"),
        (_manifest(), [("media/extra", b"x")], "unsafe_entry"),
        (_manifest(media=[_media("a", b"good")]), [("media/a", b"evil")], "integrity"),
        (_manifest(media=[_media("a", b"x")]), [], "integrity"),
    ],
)
def test_invalid_archives_are_rejected_before_writing(
    tmp_path: Path, manifest: dict[str, object], entries: list[tuple[str, bytes]], stage: str
) -> None:
    path = _tar(tmp_path / "bad.tar.gz", manifest, list(entries))
    with pytest.raises(archive.ArchiveError) as failure:
        _read(path)
    assert failure.value.stage == stage
    assert not (tmp_path / "evil").exists()


def test_links_and_truncation_are_rejected(tmp_path: Path) -> None:
    link = tarfile.TarInfo("media/link")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    with pytest.raises(archive.ArchiveError) as failure:
        _read(_tar(tmp_path / "link.tar.gz", _manifest(), [link]))
    assert failure.value.stage == "unsafe_entry"
    valid = _tar(tmp_path / "ok.tar.gz", _manifest(), [])
    truncated = tmp_path / "short.tar.gz"
    truncated.write_bytes(valid.read_bytes()[:40])
    with pytest.raises(archive.ArchiveError) as failure:
        _read(truncated)
    assert failure.value.stage == "archive"


def test_limits_are_enforced(tmp_path: Path) -> None:
    data = b"z" * 20_000
    path = _tar(
        tmp_path / "big.tar.gz", _manifest(media=[_media("big", data)]), [("media/big", data)]
    )
    with pytest.raises(archive.ArchiveError) as failure:
        _read(path)
    assert failure.value.stage == "limits"


def test_collect_media_skips_secrets_and_excluded_trees(tmp_path: Path) -> None:
    media = tmp_path / "media"
    (media / "lexicon").mkdir(parents=True)
    (media / "lexicon" / "lexicon.sqlite").write_bytes(b"x")
    (media / ".env.production").write_text("SECRET=1")
    (media / "tls.pem").write_text("key")
    (media / ".site-restore-abc").mkdir()
    (media / "keep.webp").write_bytes(b"image")
    found = archive.collect_media(media, [media / "lexicon"])
    assert [entry.path for _, entry in found] == ["keep.webp"]


def test_backup_location_must_not_overlap_media_or_lexicon(tmp_path: Path) -> None:
    settings = Settings(
        media_dir=tmp_path / "media",
        lexicon_dir=tmp_path / "lexicon",
        site_backup_dir=tmp_path / "media" / "backups",
    )
    with pytest.raises(SiteBackupError) as failure:
        check_locations(settings)
    assert failure.value.stage == "configuration"


def test_next_run_is_the_next_daily_utc_slot() -> None:
    before = datetime(2026, 1, 1, 3, 29, tzinfo=UTC)
    assert next_run(before, "03:30") == datetime(2026, 1, 1, 3, 30, tzinfo=UTC)
    assert next_run(datetime(2026, 1, 1, 3, 30, tzinfo=UTC), "03:30") == datetime(
        2026, 1, 2, 3, 30, tzinfo=UTC
    )


@pytest.mark.parametrize(("valid", "code"), [(True, 0), (False, 2)])
def test_cli_check_reads_stdin_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    valid: bool,
    code: int,
) -> None:
    manifest = _manifest() if valid else _manifest(version=9)
    data = _tar(tmp_path / "a.tar.gz", manifest, []).read_bytes()
    settings = Settings(site_backup_dir=tmp_path / "backups", media_dir=tmp_path / "media")
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
    assert cli.main(["check", "-"]) == code
    output = capsys.readouterr()
    assert ("Archive OK" in output.out) is valid
    assert ("FAILED at stage 'preflight'" in output.err) is not valid
    assert list((tmp_path / "backups").iterdir()) == []
