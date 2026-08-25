from __future__ import annotations

import numpy as np
import pytest

from rinne_reconstruction.mesh import confidence


def test_a_decisive_field_scores_one() -> None:
    # Every sample sits far from the iso-surface: nothing is ambiguous.
    deviation = np.full(1000, 5.0, dtype=np.float32)
    assert confidence.field_decisiveness(deviation, band_ratio=0.15, reference=0.10) == 1.0


def test_a_field_that_hovers_at_the_threshold_scores_zero() -> None:
    # Every sample sits within the ambiguity band, so the surface could have
    # gone either way anywhere.
    deviation = np.concatenate(
        [np.full(900, 0.001, dtype=np.float32), np.full(100, 1.0, dtype=np.float32)]
    )
    assert confidence.field_decisiveness(deviation, band_ratio=0.15, reference=0.10) == 0.0


def test_ambiguity_is_scaled_against_the_reference() -> None:
    # 5% of samples inside the band, against a 10% reference, is half the
    # budget spent: 1 - 0.05/0.10 = 0.5.
    deviation = np.concatenate(
        [np.full(50, 0.0001, dtype=np.float32), np.full(950, 1.0, dtype=np.float32)]
    )
    assert confidence.field_decisiveness(deviation, band_ratio=0.15, reference=0.10) == 0.5


def test_an_empty_or_constant_field_is_not_evidence_of_confidence() -> None:
    assert (
        confidence.field_decisiveness(np.zeros(0, np.float32), band_ratio=0.15, reference=0.1)
        == 0.0
    )
    # A constant field has p90 == 0, so there is no boundary to have been
    # decisive about.
    assert (
        confidence.field_decisiveness(np.zeros(500, np.float32), band_ratio=0.15, reference=0.1)
        == 0.0
    )


def test_a_closed_surface_is_fully_watertight() -> None:
    assert confidence.watertightness(is_watertight=True, boundary_edge_ratio=0.0) == 1.0


def test_boundary_edges_are_punished_eightfold() -> None:
    assert confidence.watertightness(is_watertight=False, boundary_edge_ratio=0.05) == 0.6
    # At 12.5% boundary edges the score bottoms out rather than going negative.
    assert confidence.watertightness(is_watertight=False, boundary_edge_ratio=0.5) == 0.0


@pytest.mark.parametrize(
    ("volume", "expected"),
    [
        (0.5, 1.0),  # peak occupancy
        (0.03, 0.0),  # a wisp
        (1.0, 0.0),  # a solid block filling its own bounding box
        (0.265, 0.5),  # halfway up the rising edge
        (0.75, 0.5),  # halfway down the falling edge
    ],
)
def test_volume_plausibility_is_a_triangular_window(volume: float, expected: float) -> None:
    # Unit bounding box, so volume and occupancy ratio are the same number.
    assert confidence.volume_plausibility(volume, (1.0, 1.0, 1.0)) == expected


def test_a_degenerate_bounding_box_is_not_plausible() -> None:
    assert confidence.volume_plausibility(0.5, (1.0, 0.0, 1.0)) == 0.0


WEIGHTS = confidence.ConfidenceWeights(
    field_decisiveness=0.5294,
    watertightness=0.3529,
    volume_plausibility=0.1177,
)


def _compose(
    components: dict[str, float], *, face_count: int = 2000
) -> confidence.ConfidenceBreakdown:
    return confidence.compose(
        components=components,
        weights=WEIGHTS,
        face_count=face_count,
        min_faces=100,
        low_max=0.45,
        high_min=0.70,
        calibrated=False,
    )


def test_the_score_is_the_weighted_sum_of_the_reported_components() -> None:
    breakdown = _compose(
        {"fieldDecisiveness": 0.7104, "watertightness": 1.0, "volumePlausibility": 0.0512}
    )
    # 0.7104*0.5294 + 1.0*0.3529 + 0.0512*0.1177 = 0.735012 -> 0.735
    assert breakdown.score == 0.735
    recomputed = sum(
        breakdown.weights[name] * breakdown.components[name] for name in breakdown.weights
    )
    assert round(recomputed, 4) == breakdown.score


def test_the_weights_that_produced_the_score_ship_with_it() -> None:
    breakdown = _compose(
        {"fieldDecisiveness": 1.0, "watertightness": 1.0, "volumePlausibility": 1.0}
    )
    assert breakdown.weights == {
        "fieldDecisiveness": 0.5294,
        "watertightness": 0.3529,
        "volumePlausibility": 0.1177,
    }
    assert round(sum(breakdown.weights.values()), 4) == 1.0
    assert breakdown.score == 1.0


def test_foreground_quality_is_absent_until_segmentation_ships() -> None:
    breakdown = _compose(
        {"fieldDecisiveness": 0.5, "watertightness": 0.5, "volumePlausibility": 0.5}
    )
    assert "foregroundQuality" not in breakdown.components
    assert "foregroundQuality" not in breakdown.weights


def test_too_few_faces_floors_the_score_but_still_reports_why() -> None:
    breakdown = _compose(
        {"fieldDecisiveness": 1.0, "watertightness": 1.0, "volumePlausibility": 1.0},
        face_count=12,
    )
    assert breakdown.score == 0.0
    assert breakdown.band == "low"
    # The components are still reported.
    assert breakdown.components["watertightness"] == 1.0


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, "low"),
        (0.44, "low"),
        (0.45, "medium"),
        (0.69, "medium"),
        (0.70, "high"),
        (1.0, "high"),
    ],
)
def test_bands_are_half_open_intervals(score: float, expected: str) -> None:
    assert confidence.band_for(score, low_max=0.45, high_min=0.70) == expected


def test_the_result_says_it_is_uncalibrated() -> None:
    assert (
        _compose(
            {"fieldDecisiveness": 1.0, "watertightness": 1.0, "volumePlausibility": 1.0}
        ).calibrated
        is False
    )
