from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rinne_agent.contracts.agent_job import (
    Decision,
    GateReason,
    ReconstructionRecord,
    SimulationRecord,
)
from rinne_agent.gate import Thresholds, evaluate

STAMP = datetime(2026, 8, 30, 4, 20, tzinfo=UTC)
THRESHOLDS = Thresholds(reconstruction_confidence=0.70, material_confidence=0.50)


def recon(*, confidence: float = 0.85, material: float = 0.60) -> ReconstructionRecord:
    return ReconstructionRecord.model_validate(
        {
            "requestId": "scan-9f2c41ab77d05e13",
            "meshUri": "gs://rinne-artifacts-rinnehackathon/meshes/scan-9f2c41ab77d05e13.glb",
            "confidence": confidence,
            "band": "high" if confidence >= 0.70 else "low",
            "calibrated": False,
            "material": "wood",
            "materialConfidence": material,
            "latencyMs": 4000,
        }
    )


def sim(*, verdict: str = "stable", notices: list[str] | None = None) -> SimulationRecord:
    return SimulationRecord.model_validate(
        {
            "sceneId": "scan-9f2c41ab77d05e13",
            "verdict": verdict,
            "settled": verdict != "inconclusive",
            "steps": 240,
            "tiltDegrees": 0.97,
            "driftMeters": 0.004,
            "digest": "2aa41a6cdf3d89f5",
            "notices": notices or [],
            "latencyMs": 500,
        }
    )


def test_everything_passing_reports() -> None:
    record = evaluate(reconstruction=recon(), simulation=sim(), thresholds=THRESHOLDS, at=STAMP)
    assert record.decision is Decision.report
    assert record.reasons == []


def test_the_record_names_the_rule_and_every_input_it_compared() -> None:
    """Never a bare if. The refusal has to be auditable from the document alone."""
    record = evaluate(reconstruction=recon(), simulation=sim(), thresholds=THRESHOLDS, at=STAMP)
    assert record.policy.value == "min-confidence-v1"
    assert len(record.inputs) == 3
    assert [item.name.value for item in record.inputs] == [
        "reconstruction-confidence",
        "material-confidence",
        "physics-verdict",
    ]
    assert all(item.threshold is not None for item in record.inputs)


def test_observed_and_threshold_come_from_the_same_input() -> None:
    """Otherwise the headline reads "observed 0.5 vs threshold 0.7 -> report",
    which is two different inputs' numbers put side by side, and looks like a
    policy the gate ignored."""
    record = evaluate(
        reconstruction=recon(confidence=0.85, material=0.12),
        simulation=sim(),
        thresholds=THRESHOLDS,
        at=STAMP,
    )
    assert record.observed == pytest.approx(0.12)
    assert record.threshold == pytest.approx(0.50)


def test_a_reported_job_never_shows_observed_below_threshold() -> None:
    """The exact bottle that exposed this: material 0.50 against its own 0.50 is a
    pass, but it was being printed against reconstruction's 0.70."""
    record = evaluate(
        reconstruction=recon(confidence=0.9222, material=0.50),
        simulation=sim(verdict="tipped"),
        thresholds=THRESHOLDS,
        at=STAMP,
    )
    assert record.decision is Decision.report
    assert record.observed >= record.threshold


def test_an_escalation_shows_the_input_that_actually_failed() -> None:
    record = evaluate(
        reconstruction=recon(confidence=0.22, material=0.95),
        simulation=sim(),
        thresholds=THRESHOLDS,
        at=STAMP,
    )
    assert record.observed == pytest.approx(0.22)
    assert record.threshold == pytest.approx(0.70)
    assert record.observed < record.threshold


def test_low_reconstruction_confidence_escalates() -> None:
    record = evaluate(
        reconstruction=recon(confidence=0.41), simulation=sim(), thresholds=THRESHOLDS, at=STAMP
    )
    assert record.decision is Decision.escalate
    assert GateReason.low_reconstruction_confidence in (record.reasons or [])


def test_low_material_confidence_escalates_on_its_own() -> None:
    """Section 7: reconstruction confidence OR material confidence. Either one."""
    record = evaluate(
        reconstruction=recon(confidence=0.95, material=0.10),
        simulation=sim(),
        thresholds=THRESHOLDS,
        at=STAMP,
    )
    assert record.decision is Decision.escalate
    assert record.reasons == [GateReason.low_material_confidence]


def test_inconclusive_physics_escalates_even_when_confidence_is_high() -> None:
    """The engine refusing to guess is a first-class reason to ask a human."""
    record = evaluate(
        reconstruction=recon(confidence=0.99, material=0.99),
        simulation=sim(verdict="inconclusive"),
        thresholds=THRESHOLDS,
        at=STAMP,
    )
    assert record.decision is Decision.escalate
    assert record.reasons == [GateReason.physics_inconclusive]


def test_an_unsupported_test_escalates_rather_than_reporting_a_false_stable() -> None:
    """A load test settles untouched and returns stable. That stable means nothing."""
    record = evaluate(
        reconstruction=recon(confidence=0.99, material=0.99),
        simulation=sim(verdict="stable", notices=["load-test-not-implemented"]),
        thresholds=THRESHOLDS,
        at=STAMP,
    )
    assert record.decision is Decision.escalate
    assert record.reasons == [GateReason.physics_test_unsupported]


def test_unsupported_and_inconclusive_do_not_both_fire() -> None:
    record = evaluate(
        reconstruction=recon(),
        simulation=sim(verdict="inconclusive", notices=["load-test-not-implemented"]),
        thresholds=THRESHOLDS,
        at=STAMP,
    )
    assert record.reasons == [GateReason.physics_test_unsupported]


def test_every_failing_input_contributes_its_own_reason() -> None:
    record = evaluate(
        reconstruction=recon(confidence=0.20, material=0.05),
        simulation=sim(verdict="inconclusive"),
        thresholds=THRESHOLDS,
        at=STAMP,
    )
    assert set(record.reasons or []) == {
        GateReason.low_reconstruction_confidence,
        GateReason.low_material_confidence,
        GateReason.physics_inconclusive,
    }


def test_calibration_is_reported_but_does_not_change_the_decision() -> None:
    """Section 0c: the gate reads the score; the bands only label it."""
    uncalibrated = evaluate(
        reconstruction=recon(), simulation=sim(), thresholds=THRESHOLDS, at=STAMP
    )
    assert uncalibrated.calibrated is False
    assert uncalibrated.decision is Decision.report


def test_a_value_exactly_on_the_threshold_passes() -> None:
    record = evaluate(
        reconstruction=recon(confidence=0.70, material=0.50),
        simulation=sim(),
        thresholds=THRESHOLDS,
        at=STAMP,
    )
    assert record.decision is Decision.report
