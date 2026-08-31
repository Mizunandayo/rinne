"""Section 7 steps 2 to 3, run from `triaged`: select, reconstruct, simulate, gate."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rinne_agent.agents.runtime import Selector
from rinne_agent.clients.physics import Simulator
from rinne_agent.clients.reconstruction import Reconstructor
from rinne_agent.contracts import AgentJob, ReconstructionResult, SimulationResult
from rinne_agent.contracts.agent_job import (
    Decision,
    JobActor,
    JobState,
    ReconstructionRecord,
    SelectionRecord,
    SimulationRecord,
)
from rinne_agent.errors import RuleError
from rinne_agent.gate import Thresholds, evaluate
from rinne_agent.scene import SolverSettings, build
from rinne_agent.state import transition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Decider:
    """Everything the decision half needs, injected. No module-level singletons."""

    selector: Selector
    reconstructor: Reconstructor
    simulator: Simulator
    thresholds: Thresholds
    solver: SolverSettings

    async def decide(self, job: AgentJob, *, image: bytes, mime_type: str) -> AgentJob:
        """Returns the job in awaiting_verification or reporting. Never mutates the input."""
        if job.triage is None:
            raise RuleError(
                "the job reached selection without a triage record",
                retryable=False,
                actor=JobActor.gate,
            )

        chosen = await self.selector.select(
            job_id=job.job_id,
            image=image,
            mime_type=mime_type,
            shape=job.triage.shape.value,
        )
        if chosen.output.kind == "none":
            raise RuleError(
                "test selection found nothing worth simulating",
                retryable=False,
                actor=JobActor.gate,
            )

        selection = SelectionRecord.model_validate(
            {
                "kind": chosen.output.kind,
                "rationale": chosen.output.rationale,
                "confidence": chosen.output.confidence,
                "model": chosen.model,
                "basis": "flash-selection-v1",
                "latencyMs": chosen.latency_ms,
                "promptTokens": chosen.prompt_tokens,
                "responseTokens": chosen.response_tokens,
                "label": chosen.output.label,
                "longestDimensionMeters": chosen.output.longest_dimension_meters,
            }
        )

        moved = transition(
            job,
            target=JobState.simulating,
            actor=JobActor.gate,
            summary=(
                f"Selected the {selection.kind.value} test for a "
                f"{selection.label} at {selection.longest_dimension_meters:.2f} m. "
                f"{selection.rationale}"
            ),
            model=chosen.model,
            confidence=selection.confidence,
            latency_ms=selection.latency_ms,
        ).model_copy(update={"selection": selection})

        result, recon_ms = await self.reconstructor.reconstruct(
            request_id=job.job_id,
            image=image,
            mime_type=mime_type,
            longest_dimension_meters=selection.longest_dimension_meters,
            label=selection.label,
        )
        reconstruction = _reconstruction_record(result, recon_ms)

        scene = build(
            job_id=job.job_id, result=result, kind=selection.kind.value, settings=self.solver
        )
        outcome, sim_ms = await self.simulator.simulate(scene)
        simulation = _simulation_record(outcome, sim_ms)

        record = evaluate(
            reconstruction=reconstruction, simulation=simulation, thresholds=self.thresholds
        )
        escalating = record.decision is Decision.escalate
        target = JobState.awaiting_verification if escalating else JobState.reporting
        summary = (
            "Confidence below the declared policy. Escalated for human verification: "
            + ", ".join(reason.value for reason in (record.reasons or []))
            if escalating
            else "Confidence cleared the declared policy. Report synthesis is Day 9."
        )

        logger.info(
            "gate evaluated",
            extra={
                "jobId": job.job_id,
                "decision": record.decision.value,
                "observed": record.observed,
                "threshold": record.threshold,
                "calibrated": record.calibrated,
                "verdict": simulation.verdict.value,
                "reasons": [reason.value for reason in (record.reasons or [])],
            },
        )

        decided = transition(
            moved,
            target=target,
            actor=JobActor.gate,
            summary=summary,
            confidence=record.observed,
            latency_ms=recon_ms + sim_ms,
        )
        return decided.model_copy(
            update={
                "reconstruction": reconstruction,
                "simulation": simulation,
                "gate": record,
            }
        )


def _reconstruction_record(result: ReconstructionResult, latency_ms: int) -> ReconstructionRecord:
    return ReconstructionRecord.model_validate(
        {
            "requestId": result.request_id,
            "meshUri": result.mesh.uri,
            "confidence": result.confidence.score,
            "band": result.confidence.band.value,
            "calibrated": result.confidence.calibrated,
            "material": result.material.name.value,
            "materialConfidence": result.material.confidence,
            "massKilograms": result.material.mass_kilograms,
            "faceCount": result.mesh.face_count,
            "watertight": result.mesh.watertight,
            "pipeline": result.pipeline.name.value,
            "latencyMs": latency_ms,
        }
    )


def _simulation_record(result: SimulationResult, latency_ms: int) -> SimulationRecord:
    return SimulationRecord.model_validate(
        {
            "sceneId": result.scene_id,
            "verdict": result.outcome.verdict.value,
            "settled": result.outcome.settled,
            "steps": result.outcome.steps,
            "tiltDegrees": result.outcome.tilt_degrees,
            "driftMeters": result.outcome.drift_meters,
            "digest": result.determinism.digest,
            "hullVertices": result.collider.hull_vertices,
            "notices": [notice.code.value for notice in (result.notices or [])],
            "latencyMs": latency_ms,
        }
    )
