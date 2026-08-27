"""u2netp foreground segmentation and the two numbers foregroundQuality reads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray
from PIL import Image

from rinne_reconstruction.pipeline.base import ForegroundMeasurements

#: u2netp's training resolution, and the ImageNet statistics it was trained on.
_INPUT_EDGE: Final = 320
_MEAN: Final[tuple[float, float, float]] = (0.485, 0.456, 0.406)
_STD: Final[tuple[float, float, float]] = (0.229, 0.224, 0.225)

#: Where a soft mask becomes a decision.
MASK_THRESHOLD: Final = 0.5

#: The border ring measured for cropping, as a share of the shorter edge.
BORDER_RATIO: Final = 0.02

#: Mid grey, matching TripoSR's own run.py: `rgb * a + (1 - a) * 0.5`.
_BACKGROUND_VALUE: Final = 0.5
_MEASUREMENT_PRECISION: Final = 6


@dataclass(frozen=True)
class ForegroundMask:
    """A soft mask in [0,1] at the image's own size, plus what it measures."""

    mask: NDArray[np.float32]
    measurements: ForegroundMeasurements


def measure_foreground(mask: NDArray[np.float32]) -> ForegroundMeasurements:
    """Share of the frame the subject fills and share of the border it touches."""

    if mask.size == 0:
        return ForegroundMeasurements(coverage=0.0, border_fraction=1.0)

    solid = mask >= MASK_THRESHOLD
    height, width = solid.shape
    ring = max(1, int(round(min(height, width) * BORDER_RATIO)))

    border = np.zeros_like(solid)
    border[:ring, :] = True
    border[height - ring :, :] = True
    border[:, :ring] = True
    border[:, width - ring :] = True

    coverage = float(np.count_nonzero(solid)) / float(solid.size)
    border_total = float(np.count_nonzero(border))
    border_hit = float(np.count_nonzero(solid & border))
    return ForegroundMeasurements(
        coverage=round(coverage, _MEASUREMENT_PRECISION),
        border_fraction=round(border_hit / border_total, _MEASUREMENT_PRECISION),
    )


def crop_and_composite(
    image: Image.Image,
    mask: NDArray[np.float32],
    *,
    foreground_ratio: float,
) -> Image.Image:
    """Crop to the subject, centre it on a square, and composite it on mid grey.

    This is TripoSR's own `resize_foreground` plus run.py's grey composite,
    done in one pass so the model receives exactly the framing it was trained
    on rather than whatever the photographer chose.
    """
    solid = mask >= MASK_THRESHOLD
    rows = np.flatnonzero(solid.any(axis=1))
    columns = np.flatnonzero(solid.any(axis=0))
    if rows.size == 0 or columns.size == 0:
        top, bottom, left, right = 0, solid.shape[0], 0, solid.shape[1]
    else:
        top, bottom = int(rows[0]), int(rows[-1]) + 1
        left, right = int(columns[0]), int(columns[-1]) + 1

    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)[top:bottom, left:right] / 255.0
    alpha = mask[top:bottom, left:right][..., np.newaxis]
    subject = rgb * alpha + _BACKGROUND_VALUE * (1.0 - alpha)

    height, width = subject.shape[0], subject.shape[1]
    edge = max(int(round(max(height, width) / foreground_ratio)), max(height, width))
    canvas = np.full((edge, edge, 3), _BACKGROUND_VALUE, dtype=np.float32)
    offset_y = (edge - height) // 2
    offset_x = (edge - width) // 2
    canvas[offset_y : offset_y + height, offset_x : offset_x + width] = subject

    return Image.fromarray(np.clip(canvas * 255.0, 0, 255).astype(np.uint8), mode="RGB")


class U2netpSegmenter:
    """One ONNX session, loaded once, reused for the life of the instance."""

    def __init__(self, model_path: str | Path) -> None:
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"segmentation model not found at {path}")

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._input_name = self._session.get_inputs()[0].name
        self._model_path = path

    @property
    def model_path(self) -> Path:
        return self._model_path

    def segment(self, image: Image.Image) -> ForegroundMask:
        outputs = self._session.run(None, {self._input_name: _preprocess(image)})
        prediction = np.asarray(outputs[0], dtype=np.float32)[0, 0]

        lowest = float(prediction.min())
        highest = float(prediction.max())
        if highest <= lowest:
            normalised = np.zeros_like(prediction, dtype=np.float32)
        else:
            normalised = (prediction - lowest) / (highest - lowest)

        resized = Image.fromarray((normalised * 255.0).astype(np.uint8), mode="L").resize(
            image.size, Image.Resampling.LANCZOS
        )
        mask = np.asarray(resized, dtype=np.float32) / 255.0
        return ForegroundMask(mask=mask, measurements=measure_foreground(mask))


def _preprocess(image: Image.Image) -> NDArray[np.float32]:
    """Resize to 320x320, scale by the observed peak, standardise, NCHW."""
    resized = image.convert("RGB").resize((_INPUT_EDGE, _INPUT_EDGE), Image.Resampling.LANCZOS)
    array = np.asarray(resized, dtype=np.float32)
    peak = float(array.max())
    if peak > 0.0:
        array = array / peak

    standardised = (array - np.asarray(_MEAN, dtype=np.float32)) / np.asarray(
        _STD, dtype=np.float32
    )
    return np.ascontiguousarray(standardised.transpose(2, 0, 1)[np.newaxis], dtype=np.float32)
