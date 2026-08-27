from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from rinne_reconstruction.imaging import segmentation
from rinne_reconstruction.mesh import confidence


def test_a_centred_subject_measures_its_coverage_and_a_clear_border() -> None:
    mask = np.zeros((200, 200), dtype=np.float32)
    mask[50:150, 50:150] = 1.0

    measured = segmentation.measure_foreground(mask)
    assert measured.coverage == 0.25
    assert measured.border_fraction == 0.0


def test_a_subject_filling_the_frame_touches_the_whole_border() -> None:
    measured = segmentation.measure_foreground(np.ones((100, 100), dtype=np.float32))
    assert measured.coverage == 1.0
    assert measured.border_fraction == 1.0
    # Coverage twice the 0.35 target, and the border fully occupied.
    assert (
        confidence.foreground_quality(
            coverage=measured.coverage, border_fraction=measured.border_fraction
        )
        == 0.0
    )


def test_a_mask_that_found_nothing_scores_zero_rather_than_scoring_well() -> None:
    measured = segmentation.measure_foreground(np.zeros((64, 64), dtype=np.float32))
    assert measured.coverage == 0.0
    assert measured.border_fraction == 0.0
    assert (
        confidence.foreground_quality(
            coverage=measured.coverage, border_fraction=measured.border_fraction
        )
        == 0.0
    )


def test_a_mask_with_no_pixels_at_all_reports_full_border_contact() -> None:
    """A mask of no pixels must not be able to read as perfectly framed."""
    measured = segmentation.measure_foreground(np.zeros((0, 0), dtype=np.float32))
    assert measured.coverage == 0.0
    assert measured.border_fraction == 1.0


def test_the_border_ring_is_two_percent_of_the_shorter_edge() -> None:
    mask = np.zeros((100, 400), dtype=np.float32)
    # A two-pixel band down the left edge: exactly the ring width for 100px.
    mask[:, :2] = 1.0
    measured = segmentation.measure_foreground(mask)
    assert measured.coverage == 0.005
    assert measured.border_fraction > 0.0


def test_the_subject_is_cropped_centred_and_padded_to_the_foreground_ratio() -> None:
    image = Image.new("RGB", (200, 200), (255, 0, 0))
    mask = np.zeros((200, 200), dtype=np.float32)
    mask[60:140, 80:120] = 1.0

    framed = segmentation.crop_and_composite(image, mask, foreground_ratio=0.85)

    # 80 is the longer side of the crop; round(80 / 0.85) is 94.
    assert framed.size == (94, 94)
    assert framed.mode == "RGB"

    pixels = np.asarray(framed)
    assert tuple(pixels[0, 0]) == (127, 127, 127)
    assert tuple(pixels[47, 47]) == (255, 0, 0)


def test_an_empty_mask_hands_over_the_whole_frame_rather_than_failing() -> None:
    """A photograph that segments to nothing is a low-confidence result, not a 500."""
    image = Image.new("RGB", (120, 90), (10, 20, 30))

    framed = segmentation.crop_and_composite(
        image, np.zeros((90, 120), dtype=np.float32), foreground_ratio=0.85
    )

    assert framed.size == (141, 141)
    assert np.unique(np.asarray(framed)).tolist() == [127]


def test_a_missing_segmentation_model_is_a_startup_failure(tmp_path) -> None:
    """It fails in the lifespan block, so the revision never receives traffic."""
    with pytest.raises(FileNotFoundError):
        segmentation.U2netpSegmenter(tmp_path / "u2netp.onnx")
