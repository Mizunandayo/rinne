"""Section 7 step 3. The confidence gate, as a declared policy rather than an if."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from rinne_agent.contracts.agent_job import (
    Decision,
    GateInput,
    GateReason,
    GateRecord,
    Name,
    Policy,
    ReconstructionRecord,
    SimulationRecord,
    Verdict,
)
from rinne_agent.state import now

#: The physics engine accepts a load test, applies no force, and settles to a
#: stable that means nothing. An answer the engine cannot give is a reason to ask.
_UNSUPPORTED_NOTICE: Final = "load-test-not-implemented"

_FAILED = 0.0
_PASSED = 1.0
_VERDICT_THRESHOLD = 1.0


@dataclass(frozen=True)
class Thresholds:
    """Configured, not compiled. Changing one is an env var, not a deploy."""

    reconstruction_confidence: float
    material_confidence: float


def evaluate(
    *,
    reconstruction: ReconstructionRecord,
    simulation: SimulationRecord,
    thresholds: Thresholds,
    at: datetime | None = None,
) -> GateRecord:
    """Compare every input, record all of them, then decide from what was recorded."""
    unsupported = _UNSUPPORTED_NOTICE in (simulation.notices or [])
    inconclusive = simulation.verdict is Verdict.inconclusive
    verdict_value = _FAILED if (unsupported or inconclusive) else _PASSED

    inputs = [
        GateInput(
            name=Name.reconstruction_confidence,
            value=reconstruction.confidence,
            threshold=thresholds.reconstruction_confidence,
            passed=reconstruction.confidence >= thresholds.reconstruction_confidence,
        ),
        GateInput(
            name=Name.material_confidence,
            value=reconstruction.material_confidence,
            threshold=thresholds.material_confidence,
            passed=reconstruction.material_confidence >= thresholds.material_confidence,
        ),
        GateInput(
            name=Name.physics_verdict,
            value=verdict_value,
            threshold=_VERDICT_THRESHOLD,
            passed=verdict_value >= _VERDICT_THRESHOLD,
        ),
    ]

    reasons: list[GateReason] = []
    if not inputs[0].passed:
        reasons.append(GateReason.low_reconstruction_confidence)
    if not inputs[1].passed:
        reasons.append(GateReason.low_material_confidence)
    if unsupported:
        reasons.append(GateReason.physics_test_unsupported)
    elif inconclusive:
        reasons.append(GateReason.physics_inconclusive)

    return GateRecord.model_validate(
        {
            "policy": Policy.min_confidence_v1,
            "threshold": thresholds.reconstruction_confidence,
            # The binding input: the lowest value seen is the number that decided it.
            "observed": min(item.value for item in inputs),
            "calibrated": reconstruction.calibrated,
            "decision": Decision.escalate if reasons else Decision.report,
            "inputs": inputs,
            "reasons": reasons,
            "at": at or now(),
        }
    )
