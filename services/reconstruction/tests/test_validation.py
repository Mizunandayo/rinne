from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from rinne_reconstruction.imaging.validation import (
    ImageValidationError,
    prepare_image,
    sniff_media_type,
)

LIMITS = {"max_bytes": 6_291_456, "max_pixels": 40_000_000, "max_edge": 1536}


def test_a_real_jpeg_survives_every_layer(image_bytes) -> None:
    prepared = prepare_image(image_bytes(), "image/jpeg", **LIMITS)
    assert prepared.image.mode == "RGB"
    assert prepared.longest_edge_pixels == 320


def test_declared_type_outside_the_allowlist_is_refused(image_bytes) -> None:
    with pytest.raises(ImageValidationError) as caught:
        prepare_image(image_bytes(fmt="GIF"), "image/gif", **LIMITS)
    assert caught.value.rule == "image type is not one of jpeg, png, webp"


def test_magic_bytes_must_agree_with_the_declared_type(image_bytes) -> None:
    """A PNG announced as a JPEG is refused.

    This is the layer that stops a polyglot: a file that a strict parser reads
    as one format and a lenient one reads as another only works if the declared
    type is never checked against the bytes.
    """
    with pytest.raises(ImageValidationError) as caught:
        prepare_image(image_bytes(fmt="PNG"), "image/jpeg", **LIMITS)
    assert caught.value.rule == "image content does not match its declared type"


def test_bytes_that_are_not_an_image_at_all_are_refused() -> None:
    with pytest.raises(ImageValidationError) as caught:
        prepare_image(b"#!/bin/sh\nrm -rf /\n", "image/png", **LIMITS)
    assert caught.value.rule == "image content does not match any allowed format"


def test_an_empty_part_is_refused() -> None:
    with pytest.raises(ImageValidationError):
        prepare_image(b"", "image/jpeg", **LIMITS)


def test_a_part_over_the_size_limit_is_refused(image_bytes) -> None:
    with pytest.raises(ImageValidationError) as caught:
        prepare_image(image_bytes(), "image/jpeg", **{**LIMITS, "max_bytes": 64})
    assert caught.value.rule == "image exceeds the per-image size limit"


def test_the_pixel_ceiling_is_read_from_the_header_not_from_a_decode(image_bytes) -> None:
    """A decompression bomb is refused on its DIMENSIONS.

    320x240 with a ceiling of 1000 pixels stands in for 60000x60000 with a
    ceiling of 40 million: the point is that the rejection happens after the
    header and before a buffer that size is ever allocated.
    """
    with pytest.raises(ImageValidationError) as caught:
        prepare_image(image_bytes(), "image/jpeg", **{**LIMITS, "max_pixels": 1000})
    assert caught.value.rule == "image exceeds the pixel-count limit"


def test_multi_frame_images_are_refused() -> None:
    """An animated PNG is still a PNG to every check before this one.

    APNG carries the same magic bytes as a still PNG, so the allowlist and the
    magic-byte layer both wave it through. This is the layer that stops it, and
    it matters because "which frame did you reconstruct" has no good answer and
    the unused frames are free payload space for a parser differential.
    """
    buffer = BytesIO()
    frames = [Image.new("RGB", (32, 32), (200, 30, 30)) for _ in range(3)]
    frames[0].save(buffer, format="PNG", save_all=True, append_images=frames[1:])

    assert sniff_media_type(buffer.getvalue()) == "image/png"
    with pytest.raises(ImageValidationError) as caught:
        prepare_image(buffer.getvalue(), "image/png", **LIMITS)
    assert caught.value.rule == "multi-frame images are not accepted"


def test_the_longest_edge_is_bounded(image_bytes) -> None:
    prepared = prepare_image(
        image_bytes(size=(4000, 1000)), "image/jpeg", **{**LIMITS, "max_edge": 512}
    )
    assert prepared.longest_edge_pixels == 512
    assert max(prepared.image.size) == 512


def test_exif_is_gone_after_re_encoding() -> None:
    """Layer 7 in one assertion: the service holds pixels it decoded itself.

    A phone photograph carries GPS in EXIF. The image handed to the pipeline
    has no EXIF at all, which satisfies section 12's no-PII-beyond-necessity
    rule mechanically rather than by anyone remembering to strip it.
    """
    buffer = BytesIO()
    source = Image.new("RGB", (64, 48), (120, 90, 50))
    exif = source.getexif()
    exif[274] = 6  # Orientation: rotate 90 degrees
    source.save(buffer, format="JPEG", exif=exif)

    original = Image.open(BytesIO(buffer.getvalue()))
    assert dict(original.getexif())

    prepared = prepare_image(buffer.getvalue(), "image/jpeg", **LIMITS)
    assert not dict(prepared.image.getexif())
    # Orientation 6 is a quarter turn, so the re-encoded image is 48x64 rather
    # than 64x48. exif_transpose ran BEFORE the metadata was dropped.
    assert prepared.image.size == (48, 64)


@pytest.mark.parametrize(
    ("fmt", "media_type"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_every_allowed_format_round_trips(fmt: str, media_type: str, image_bytes) -> None:
    data = image_bytes(fmt=fmt)
    assert sniff_media_type(data) == media_type
    assert prepare_image(data, media_type, **LIMITS).image.mode == "RGB"


def test_sniffing_ignores_what_the_client_claimed(image_bytes) -> None:
    assert sniff_media_type(image_bytes(fmt="PNG")) == "image/png"
    assert sniff_media_type(b"not an image") is None
