from __future__ import annotations

import pytest

from rinne_agent.clients.physics import HttpSimulator, StubSimulator, build_simulator
from rinne_agent.clients.reconstruction import (
    HttpReconstructor,
    StubReconstructor,
    build_reconstructor,
)
from rinne_agent.gcp.tokens import StaticTokenSource
from rinne_agent.scene import SolverSettings, build

SOLVER = SolverSettings(
    timestep_seconds=1 / 60,
    max_steps=900,
    seed=42,
    ground_friction=0.6,
    ground_restitution=0.1,
    tip_force_ratio=0.5,
    tip_height_ratio=0.9,
    tip_direction_degrees=0.0,
    tip_duration_seconds=0.2,
    drop_height_meters=0.1,
    load_multiple=2.0,
)


def test_the_factories_pick_by_configuration_not_by_fallback() -> None:
    tokens = StaticTokenSource()
    assert isinstance(
        build_reconstructor(mode="memory", base_url="", tokens=tokens, timeout_seconds=1.0),
        StubReconstructor,
    )
    assert isinstance(
        build_reconstructor(
            mode="http", base_url="https://example.invalid", tokens=tokens, timeout_seconds=1.0
        ),
        HttpReconstructor,
    )
    assert isinstance(
        build_simulator(mode="memory", base_url="", tokens=tokens, timeout_seconds=1.0),
        StubSimulator,
    )
    assert isinstance(
        build_simulator(
            mode="http", base_url="https://example.invalid", tokens=tokens, timeout_seconds=1.0
        ),
        HttpSimulator,
    )


async def test_the_stub_reconstruction_is_contract_valid_end_to_end() -> None:
    result, latency = await StubReconstructor().reconstruct(
        request_id="scan-9f2c41ab77d05e13", image=b"", mime_type="image/png"
    )
    assert result.request_id == "scan-9f2c41ab77d05e13"
    assert result.mesh.uri.startswith("gs://")
    assert 0.0 <= result.confidence.score <= 1.0
    assert latency >= 0


async def test_the_stub_reconstruction_confidence_is_settable_for_the_gate() -> None:
    result, _ = await StubReconstructor(confidence=0.30).reconstruct(
        request_id="scan-9f2c41ab77d05e13", image=b"", mime_type="image/png"
    )
    assert result.confidence.score == pytest.approx(0.30)
    assert result.confidence.band.value == "low"


async def test_the_stub_simulation_echoes_the_scene_it_was_given() -> None:
    built, _ = await StubReconstructor().reconstruct(
        request_id="scan-9f2c41ab77d05e13", image=b"", mime_type="image/png"
    )
    scene = build(job_id="scan-9f2c41ab77d05e13", result=built, kind="tip", settings=SOLVER)
    outcome, _ = await StubSimulator().simulate(scene)
    assert outcome.scene_id == scene.scene_id
    assert outcome.determinism.seed == scene.solver.seed
    assert outcome.collider.mass_kilograms == scene.body.mass_kilograms


@pytest.mark.parametrize("verdict", ["stable", "tipped", "slid", "inconclusive"])
async def test_every_verdict_the_contract_allows_can_be_produced(verdict: str) -> None:
    built, _ = await StubReconstructor().reconstruct(
        request_id="scan-9f2c41ab77d05e13", image=b"", mime_type="image/png"
    )
    scene = build(job_id="scan-9f2c41ab77d05e13", result=built, kind="tip", settings=SOLVER)
    outcome, _ = await StubSimulator(verdict=verdict).simulate(scene)
    assert outcome.outcome.verdict.value == verdict
    assert outcome.outcome.settled is (verdict != "inconclusive")


async def test_the_load_notice_survives_into_the_result() -> None:
    """The gate reads this notice, so it has to travel intact."""
    built, _ = await StubReconstructor().reconstruct(
        request_id="scan-9f2c41ab77d05e13", image=b"", mime_type="image/png"
    )
    scene = build(job_id="scan-9f2c41ab77d05e13", result=built, kind="load", settings=SOLVER)
    outcome, _ = await StubSimulator(notices=["load-test-not-implemented"]).simulate(scene)
    assert [notice.code.value for notice in (outcome.notices or [])] == [
        "load-test-not-implemented"
    ]
