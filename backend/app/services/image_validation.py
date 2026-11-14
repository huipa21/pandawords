import io
import warnings

from PIL import Image, UnidentifiedImageError

from app.core.errors import AppError
from app.domain.images import MAX_BYTES, MAX_FRAMES, MAX_PIXELS, MAX_TOTAL_PIXELS

FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}


def validate(content: bytes, declared_mime: str) -> str:
    if not content or len(content) > MAX_BYTES:
        raise AppError("image.size", 422, "Image must contain between 1 byte and 10 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                mime = FORMATS.get(image.format or "")
                if mime is None or mime != declared_mime:
                    raise ValueError("Unsupported or mismatched format")
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                total = 0
                frames = 0
                while True:
                    frames += 1
                    pixels = image.width * image.height
                    total += pixels
                    if frames > MAX_FRAMES or pixels > MAX_PIXELS or total > MAX_TOTAL_PIXELS:
                        raise ValueError("Image dimensions exceeded")
                    image.load()
                    try:
                        image.seek(frames)
                    except EOFError:
                        break
                return mime
    except (
        OSError,
        ValueError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise AppError("image.invalid", 422, "Invalid, unsupported or over-limit image.") from None
