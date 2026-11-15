import io
import json
import tarfile
from pathlib import Path

import pytest

from app.core.errors import BundleError
from app.domain.bundle import BundleData, dump_data
from app.domain.bundle_serialize import serialize_bundle
from app.services.bundle_archive import ArchiveLimits, ArchiveMember, read_archive, write_archive
from app.services.bundle_io import export_bundle, load_bundle
from tests import bundle_support as fx

USER = frozenset({"pandawords.user"})


def _data() -> BundleData:
    return serialize_bundle(fx.OWNER, "pandawords.user", fx.source())


def _export(tmp_path: Path) -> Path:
    media = tmp_path / "media-src"
    media.mkdir(parents=True)
    _, files = fx.media_files(media)
    target = tmp_path / "out" / "backup.tar.gz"
    export_bundle(target, fx.header(), _data(), files)
    return target


def _tar(path: Path, members: list[tuple[tarfile.TarInfo, bytes]]) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for info, data in members:
            tar.addfile(info, io.BytesIO(data) if info.isreg() else None)
    return path


def _file(name: str, data: bytes) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    return info, data


def _manifest(entries: list[tuple[str, bytes]], version: int = 1) -> bytes:
    import hashlib

    header = json.loads(fx.header().model_dump_json())
    rows = [
        {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        for name, data in entries
    ]
    return json.dumps(header | {"version": version, "entries": rows}).encode()


def _listing(root: Path) -> list[str]:
    return sorted(path.name for path in root.iterdir()) if root.exists() else []


def _staged(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()] if root.exists() else []


def test_export_load_round_trip(tmp_path: Path) -> None:
    archive = _export(tmp_path)
    assert [p.name for p in archive.parent.iterdir()] == ["backup.tar.gz"]
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert names[:2] == ["manifest.json", "data.json"] and len(names) == 4
    loaded = load_bundle(archive, tmp_path / "staging", expected_formats=USER)
    try:
        assert dump_data(loaded.data) == dump_data(_data())
        image = next(m for m in loaded.data.media if m.kind == "image")
        assert loaded.media_path(image.file).read_bytes() == fx.IMAGE_BYTES
        assert loaded.archive.manifest.attribution
    finally:
        loaded.close()
    assert _staged(tmp_path / "staging") == []


def test_repeated_export_is_byte_identical(tmp_path: Path) -> None:
    first = _export(tmp_path / "a").read_bytes()
    assert _export(tmp_path / "b").read_bytes() == first


def test_failed_export_publishes_nothing(tmp_path: Path) -> None:
    media = tmp_path / "m"
    media.mkdir()
    _, files = fx.media_files(media)
    wrong = {name: next(iter(files.values())) for name in files}  # content != address
    target = tmp_path / "out" / "x.tar.gz"
    with pytest.raises(BundleError) as caught:
        export_bundle(target, fx.header(), _data(), wrong)
    assert caught.value.code == "bundle.integrity"
    assert _listing(tmp_path / "out") == []
    with pytest.raises(BundleError):
        export_bundle(target, fx.header(), _data(), {})
    with pytest.raises(BundleError):
        write_archive(
            target,
            fx.header(),
            [ArchiveMember("data.json", b"{}")],
            verify=lambda _: (_ for _ in ()).throw(BundleError("boom", "archive")),
        )
    assert _listing(tmp_path / "out") == []


def test_unsupported_version_fails_before_extracting(tmp_path: Path) -> None:
    data = b"{}"
    archive = _tar(
        tmp_path / "v2.tar.gz",
        [
            _file("manifest.json", _manifest([("data.json", data)], version=2)),
            _file("data.json", data),
        ],
    )
    with pytest.raises(BundleError) as caught:
        read_archive(archive, tmp_path / "staging")
    assert caught.value.code == "bundle.unsupported_version"
    assert _staged(tmp_path / "staging") == []


def _symlink() -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo("data.json")
    info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
    return info, b""


def _device() -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo("data.json")
    info.type = tarfile.CHRTYPE
    return info, b""


@pytest.mark.parametrize(
    ("members", "reason"),
    [
        ([("data.json", b"{}")], "missing_manifest"),
        ([("manifest.json", None), ("../data.json", b"{}")], "unsafe_entry"),
        ([("manifest.json", None), ("/data.json", b"{}")], "unsafe_entry"),
        ([("manifest.json", None), ("media\\..\\x", b"{}")], "unsafe_entry"),
        ([("manifest.json", None), ("symlink", b"")], "unsafe_entry"),
        ([("manifest.json", None), ("device", b"")], "unsafe_entry"),
        ([("manifest.json", None), ("data.json", b"{}"), ("extra.txt", b"x")], "unexpected_entry"),
        ([("manifest.json", None), ("data.json", b"{}"), ("data.json", b"{}")], "unexpected_entry"),
        ([("manifest.json", None)], "missing_entry"),
        ([("manifest.json", None), ("data.json", b"{]")], "integrity"),
    ],
)
def test_unsafe_archives_are_rejected(
    tmp_path: Path, members: list[tuple[str, bytes | None]], reason: str
) -> None:
    manifest = _manifest([("data.json", b"{}")])
    built = []
    for name, data in members:
        if name == "symlink":
            built.append(_symlink())
        elif name == "device":
            built.append(_device())
        else:
            built.append(_file(name, manifest if data is None else data))
    archive = _tar(tmp_path / "bad.tar.gz", built)
    with pytest.raises(BundleError) as caught:
        read_archive(archive, tmp_path / "staging")
    assert caught.value.code == f"bundle.{reason}"
    assert _staged(tmp_path / "staging") == []


def test_limits_are_enforced(tmp_path: Path) -> None:
    archive = _export(tmp_path)
    for limits, reason in (
        (ArchiveLimits(max_entries=2), "too_many_entries"),
        (ArchiveLimits(max_entry_bytes=8), "entry_too_large"),
        (ArchiveLimits(max_total_bytes=8), "too_large"),
        (ArchiveLimits(max_archive_bytes=8), "too_large"),
    ):
        with pytest.raises(BundleError) as caught:
            read_archive(archive, tmp_path / "staging", limits=limits)
        assert caught.value.code == f"bundle.{reason}"
    assert _staged(tmp_path / "staging") == []


def test_malformed_and_wrong_format_archives(tmp_path: Path) -> None:
    junk = tmp_path / "junk.tar.gz"
    junk.write_bytes(b"not a gzip stream")
    with pytest.raises(BundleError) as caught:
        read_archive(junk, tmp_path / "staging")
    assert caught.value.code == "bundle.malformed_archive"
    archive = _export(tmp_path)
    with pytest.raises(BundleError) as caught:
        load_bundle(
            archive, tmp_path / "staging", expected_formats=frozenset({"pandawords.project"})
        )
    assert caught.value.code == "bundle.unexpected_format"
    assert _staged(tmp_path / "staging") == []
