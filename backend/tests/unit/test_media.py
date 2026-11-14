import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError
from surrealdb import RecordID

from app.domain.media import Media, MediaCreate, validate_path
from app.services.media import _file


@pytest.mark.parametrize(
    "path",
    [
        "../secret.mp3",
        "audio/../secret.mp3",
        "/audio/file.mp3",
        "audio//file.mp3",
        "audio\\file.mp3",
        "C:/file.mp3",
        "audio/C:file.mp3",
        "audio/%2e%2e.mp3",
        "audio/file.mp3\nX-Injected: yes",
        "audio/CON.mp3",
        "audio/file.mp3.",
        "//server/share.mp3",
        "audio/./file.mp3",
    ],
)
def test_reject_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError, match="Invalid media path"):
        validate_path(path)


def test_metadata_kind_mime_and_path_validation() -> None:
    values = {
        "target": RecordID("lexeme", ["en", "test", "noun", 1]),
        "kind": "audio",
        "mime": "audio/mpeg",
        "source": "wiktionary",
    }
    assert MediaCreate.model_validate(values).mime == "audio/mpeg"
    for changes in (
        {"kind": "video"},
        {"mime": "text/html"},
        {"mime": "image/png"},
        {"source": "unknown"},
        {"target": RecordID("user", "private")},
        {"kind": "image", "mime": "image/png", "accent": "US"},
    ):
        with pytest.raises(ValidationError):
            MediaCreate.model_validate({**values, **changes})
    for path in ("audio/../../secret.mp3", "image/file.mp3", "audio/file.png"):
        with pytest.raises(ValidationError):
            Media.model_validate({**values, "id": RecordID("media", "test"), "path": path})


@pytest.mark.parametrize("escape", [False, True])
def test_containment_and_symlink_rejected(escape: bool) -> None:
    from tempfile import TemporaryDirectory

    # Keep test storage in the worktree, not the system temporary directory.
    with TemporaryDirectory(dir=Path.cwd(), prefix=".media-unit-") as directory:
        root = Path(directory) / "media"
        root.mkdir()
        assert _file(root, "audio/file.mp3") == root / "audio" / "file.mp3"
        outside = (root.parent if escape else root) / "outside"
        outside.mkdir()
        try:
            (root / "audio").symlink_to(outside, target_is_directory=True)
        except OSError:
            subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(root / "audio"), str(outside)],
                check=True,
                capture_output=True,
            )
        with pytest.raises(ValueError):
            _file(root, "audio/file.mp3")
