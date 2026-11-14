import io

import pytest
from PIL import Image

from app.core.errors import AppError
from app.domain.images import MAX_BYTES
from app.services import image_validation


def picture(fmt: str = "PNG", *, size: tuple[int, int] = (4, 4), frames: int = 1) -> bytes:
    output = io.BytesIO()
    images = [Image.new("RGB", size, (i % 256, 20, 30)) for i in range(frames)]
    images[0].save(output, format=fmt, save_all=frames > 1, append_images=images[1:])
    return output.getvalue()


@pytest.mark.parametrize(
    ("fmt", "mime"),
    [
        ("JPEG", "image/jpeg"),
        ("PNG", "image/png"),
        ("WEBP", "image/webp"),
        ("GIF", "image/gif"),
    ],
)
def test_actual_decode_all_formats(fmt: str, mime: str) -> None:
    content = picture(fmt)
    assert image_validation.validate(content, mime) == mime
    with pytest.raises(AppError):
        image_validation.validate(content, "image/not-real")
    with pytest.raises(AppError):
        image_validation.validate(content[: len(content) // 2], mime)


@pytest.mark.parametrize("content", [b"", b"not an image", b"<svg></svg>"])
def test_invalid(content: bytes) -> None:
    with pytest.raises(AppError):
        image_validation.validate(content, "image/png")


def test_encoded_exact_boundary() -> None:
    content = picture()
    content += b"\0" * (MAX_BYTES - len(content))
    assert image_validation.validate(content, "image/png") == "image/png"
    with pytest.raises(AppError):
        image_validation.validate(content + b"\0", "image/png")


def test_pixel_and_total_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(image_validation, "MAX_PIXELS", 16)
    monkeypatch.setattr(image_validation, "MAX_TOTAL_PIXELS", 32)
    assert image_validation.validate(picture("GIF", frames=2), "image/gif")
    with pytest.raises(AppError):
        image_validation.validate(picture("GIF", frames=3), "image/gif")
    with pytest.raises(AppError):
        image_validation.validate(picture(size=(5, 4)), "image/png")


def test_animation_frames() -> None:
    assert image_validation.validate(picture("GIF", size=(1, 1), frames=100), "image/gif")
    with pytest.raises(AppError):
        image_validation.validate(picture("GIF", size=(1, 1), frames=101), "image/gif")
