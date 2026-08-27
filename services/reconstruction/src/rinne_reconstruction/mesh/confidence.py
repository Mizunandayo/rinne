"""The confidence scalar: four measured components, transmitted weights."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray

PRECISION: Final = 4

#: Occupancy window for volumePlausibility: peaks at 0.5, zero at both ends.
_VOLUME_PEAK: Final = 0.5
_VOLUME_FLOOR: Final = 0.03
_VOLUME_CEILING: Final = 1.0

#: How hard a boundary edge is punished. At 12.5% boundary edges the score is 0.
_BOUNDARY_PENALTY: Final = 8.0


_FOREGROUND_TARGET_COVERAGE: Final = 0.35
_FOREGROUND_BORDER_PENALTY: Final = 4.0

Band = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ConfidenceWeights:
    """The weights used for one response. They must sum to 1.0 at 4dp."""

    field_decisiveness: float
    watertightness: float
    volume_plausibility: float
    foreground_quality: float | None = None

    def as_payload(self) -> dict[str, float]:
        payload = {
            "fieldDecisiveness": self.field_decisiveness,
            "watertightness": self.watertightness,
            "volumePlausibility": self.volume_plausibility,
        }
        if self.foreground_quality is not None:
            payload["foregroundQuality"] = self.foreground_quality
        return payload

    def without_foreground_quality(self) -> ConfidenceWeights:
        """Rescale the remaining three so they still sum to exactly 1.0 at 4dp.

        The residual is absorbed by volume_plausibility rather than spread, so
        the result is one exact set of numbers rather than a rounding argument.
        """
        if self.foreground_quality is None:
            return self

        remaining = 1.0 - self.foreground_quality
        if remaining <= 0.0:
            raise ValueError("the foregroundQuality weight leaves nothing to rescale")

        field = round(self.field_decisiveness / remaining, PRECISION)
        water = round(self.watertightness / remaining, PRECISION)
        return ConfidenceWeights(
            field_decisiveness=field,
            watertightness=water,
            volume_plausibility=round(1.0 - field - water, PRECISION),
        )


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """Score, band, and the evidence behind both."""

    score: float
    band: Band
    calibrated: bool
    components: dict[str, float]
    weights: dict[str, float]


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _round(value: float) -> float:
    return round(_clamp(value), PRECISION)


def field_decisiveness(
    deviation: NDArray[np.float32],
    *,
    band_ratio: float,
    reference: float,
) -> float:
    """How far the density field sat from the iso-surface it was cut at.

    A field that hovers near the threshold everywhere produced a surface that
    could have gone either way. The band is defined relative to the field's own
    spread (p90) rather than as an absolute number, because the field's units
    are whatever the pipeline chose - an absolute band would mean something
    different for the stub than for TripoSR.
    """
    if deviation.size == 0:
        return 0.0

    scale = float(np.percentile(deviation, 90))
    if scale <= 0.0:
        # Every sample sits exactly on the iso-surface, or the field is
        # constant. Either way there is no evidence of a decisive boundary.
        return 0.0

    band = band_ratio * scale
    ambiguous_fraction = float(np.count_nonzero(deviation < band)) / float(deviation.size)
    return _round(1.0 - ambiguous_fraction / reference)


def watertightness(*, is_watertight: bool, boundary_edge_ratio: float) -> float:
    """1.0 for a closed surface, otherwise scaled by how open it is."""
    if is_watertight:
        return 1.0
    return _round(1.0 - boundary_edge_ratio * _BOUNDARY_PENALTY)


def foreground_quality(*, coverage: float, border_fraction: float) -> float:
    """framing * cropping, measured from the segmentation mask.

    Multiplied rather than averaged: a subject too small to reconstruct and a
    subject running off the edge of the frame are independently fatal, so
    either one alone has to be able to take the component to zero.
    """
    framing = _clamp(
        1.0 - abs(coverage - _FOREGROUND_TARGET_COVERAGE) / _FOREGROUND_TARGET_COVERAGE
    )
    cropping = _clamp(1.0 - min(1.0, border_fraction * _FOREGROUND_BORDER_PENALTY))
    return _round(framing * cropping)


def volume_plausibility(volume: float, extent: tuple[float, float, float]) -> float:
    """Bounding-box occupancy through a triangular window peaking at 0.5.

    Catches both failure shapes at once: a wisp that occupies almost none of
    its box, and a solid block that occupies all of it. Real objects sit in
    between.
    """
    bbox_volume = extent[0] * extent[1] * extent[2]
    if bbox_volume <= 0.0:
        return 0.0

    ratio = abs(volume) / bbox_volume
    if ratio <= _VOLUME_FLOOR or ratio >= _VOLUME_CEILING:
        return 0.0
    if ratio <= _VOLUME_PEAK:
        return _round((ratio - _VOLUME_FLOOR) / (_VOLUME_PEAK - _VOLUME_FLOOR))
    return _round((_VOLUME_CEILING - ratio) / (_VOLUME_CEILING - _VOLUME_PEAK))


def band_for(score: float, *, low_max: float, high_min: float) -> Band:
    if score < low_max:
        return "low"
    if score >= high_min:
        return "high"
    return "medium"


def compose(
    *,
    components: dict[str, float],
    weights: ConfidenceWeights,
    face_count: int,
    min_faces: int,
    low_max: float,
    high_min: float,
    calibrated: bool,
) -> ConfidenceBreakdown:
    """Combine the components, apply the hard floor, and pick a band.

    The floor is not a weight of zero: a mesh with 12 faces should report 0.0
    even if every component happens to look good, because there is nothing
    there to be confident about. The components are still reported, so the
    reason is visible rather than hidden behind a single number.
    """
    weight_map = weights.as_payload()
    if set(weight_map) != set(components):
        raise ValueError("confidence components and weights must cover the same names")

    raw = sum(weight_map[name] * components[name] for name in weight_map)
    score = 0.0 if face_count < min_faces else _round(raw)

    return ConfidenceBreakdown(
        score=score,
        band=band_for(score, low_max=low_max, high_min=high_min),
        calibrated=calibrated,
        components={name: _round(value) for name, value in components.items()},
        weights=weight_map,
    )
