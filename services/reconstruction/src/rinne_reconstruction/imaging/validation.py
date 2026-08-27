"""Upload validation: seven layers, in order, before the model sees anything.

Layers 1 and 2 are size checks and live at the edges - BodyLimitMiddleware
rejects an oversized DECLARED length before a byte is read, and the route
counts the ACTUAL bytes as it reads them, because Content-Length is a claim.
Layers 3 to 7 are per-image and live here.

Every rejection names the RULE. Never the bytes, never the filename, never a
library message: those leak the parser's internals and, in the filename's case,
echo attacker-controlled text straight back.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from typing import Final

from PIL import Image, ImageOps

#: The allowlist is a security control, not an operational knob, so it is a
#: module constant rather than a setting. Adding a format means auditing its
#: decoder, which is a code change.
ALLOWED_MEDIA_TYPES: Final[frozenset[str]] = frozenset({"image/jpeg", "image/png", "image/webp"})

_PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC: Final = b"\xff\xd8\xff"


class ImageValidationError(ValueError):
    """One image failed one validation layer. ``rule`` is safe to return."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


@dataclass(frozen=True)
class PreparedImage:
    """An image the service produced itself, from pixels it decoded itself."""

    image: Image.Image
    longest_edge_pixels: int


def sniff_media_type(data: bytes) -> str | None:
    """Media type according to the bytes, ignoring anything the client declared."""
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@contextmanager
def _pixel_ceiling(limit: int) -> Iterator[None]:
    """Bound Pillow's decompression-bomb ceiling for the duration of one decode.

    Image.MAX_IMAGE_PIXELS is process-global, so it is restored on the way out.
    Setting it to None - Pillow's "no limit" - is what a bomb needs to work.
    """
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = limit
    try:
        yield
    finally:
        Image.MAX_IMAGE_PIXELS = previous


def prepare_image(
    data: bytes,
    declared_type: str | None,
    *,
    max_bytes: int,
    max_pixels: int,
    max_edge: int,
) -> PreparedImage:
    """Run layers 3 to 7 and return an image built from re-encoded pixels."""
    # -- layer 2, per part: the actual size of this part ----------------
    if len(data) == 0:
        raise ImageValidationError("image part is empty")
    if len(data) > max_bytes:
        raise ImageValidationError("image exceeds the per-image size limit")

    # -- layer 3: the declared type, treated strictly as a hint ---------
    normalised = (declared_type or "").split(";", 1)[0].strip().lower()
    if normalised not in ALLOWED_MEDIA_TYPES:
        raise ImageValidationError("image type is not one of jpeg, png, webp")

    # -- layer 4: magic bytes, and they must agree with the declaration --
    sniffed = sniff_media_type(data)
    if sniffed is None:
        raise ImageValidationError("image content does not match any allowed format")
    if sniffed != normalised:
        raise ImageValidationError("image content does not match its declared type")

    # -- layer 5: header-only decode -----------------------------------
    # Image.open is lazy: it reads the header and stops.
    try:
        with Image.open(BytesIO(data)) as probe:
            width, height = probe.size
            frames = getattr(probe, "n_frames", 1)
            if width <= 0 or height <= 0:
                raise ImageValidationError("image reports a zero dimension")
            if width * height > max_pixels:
                raise ImageValidationError("image exceeds the pixel-count limit")
            if frames > 1:
                # An animation is a container of images.
                raise ImageValidationError("multi-frame images are not accepted")
            probe.verify()
    except ImageValidationError:
        raise
    except Exception as exc:
        raise ImageValidationError("image header could not be decoded") from exc

    # -- layer 6: bounded full decode ----------------------------------
    # verify() leaves the file object unusable by design, so this reopens.
    try:
        with _pixel_ceiling(max_pixels), Image.open(BytesIO(data)) as source:
            source.load()

            # -- layer 7: re-encode ------------------------------------
            # exif_transpose FIRST: orientation lives in EXIF, and dropping
            # EXIF before applying it silently rotates every phone photo.
            upright = ImageOps.exif_transpose(source) or source
            rgb = upright.convert("RGB")
    except ImageValidationError:
        raise
    except Exception as exc:
        raise ImageValidationError("image could not be decoded") from exc

    if max(rgb.size) > max_edge:
        rgb.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

    return PreparedImage(image=rgb, longest_edge_pixels=max(rgb.size))
