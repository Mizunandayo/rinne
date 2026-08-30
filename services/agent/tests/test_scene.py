from __future__ import annotations

import json
from pathlib import Path

import pytest

from rinne_agent.clients.reconstruction import StubReconstructor
from rinne_agent.contracts import ReconstructionResult
from rinne_agent.scene import SolverSettings, build

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "schemas"
    / "scene-description.schema.json"
)

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

JOB_ID = "scan-9f2c41ab77d05e13"


async def result() -> ReconstructionResult:
    built, _ = await StubReconstructor().reconstruct(
        request_id=JOB_ID, image=b"", mime_type="image/png"
    )
    return built


async def test_a_tip_scene_is_contract_valid() -> None:
    scene = build(job_id=JOB_ID, result=await result(), kind="tip", settings=SOLVER)
    assert scene.scene_id == JOB_ID
    assert scene.test.kind.value == "tip"
    assert scene.solver.seed == 42


async def test_the_push_is_scaled_to_the_body_not_fixed_in_newtons() -> None:
    """Section 0c measured tipping at 0.51 of body weight. A constant force is
    meaningless across masses, so this asserts the scaling, not a magic number."""
    built = await result()
    scene = build(job_id=JOB_ID, result=built, kind="tip", settings=SOLVER)
    expected = built.material.mass_kilograms * 9.81 * SOLVER.tip_force_ratio
    assert scene.test.force_newtons == pytest.approx(expected, abs=1e-3)


async def test_the_push_lands_near_the_top() -> None:
    scene = build(job_id=JOB_ID, result=await result(), kind="tip", settings=SOLVER)
    assert scene.test.push_height_ratio == 0.9


async def test_a_drop_scene_starts_above_the_ground_plane() -> None:
    scene = build(job_id=JOB_ID, result=await result(), kind="drop", settings=SOLVER)
    assert scene.test.kind.value == "drop"
    assert scene.body.initial_translation.y == pytest.approx(SOLVER.drop_height_meters)


async def test_a_non_drop_scene_starts_seated_on_the_ground() -> None:
    """Normalisation already put the lowest point at y=0."""
    scene = build(job_id=JOB_ID, result=await result(), kind="tip", settings=SOLVER)
    assert scene.body.initial_translation.y == 0.0


async def test_a_load_scene_sizes_the_contact_from_the_footprint() -> None:
    built = await result()
    scene = build(job_id=JOB_ID, result=built, kind="load", settings=SOLVER)
    footprint = min(built.mesh.extent.x, built.mesh.extent.z)
    assert scene.test.contact_radius == pytest.approx(footprint * 0.25, abs=1e-4)
    assert scene.test.load_kilograms == pytest.approx(built.material.mass_kilograms * 2.0, abs=1e-3)


async def test_the_body_carries_the_material_estimate() -> None:
    built = await result()
    scene = build(job_id=JOB_ID, result=built, kind="tip", settings=SOLVER)
    assert scene.body.mass_kilograms == built.material.mass_kilograms
    assert scene.body.friction == built.material.friction
    assert scene.body.restitution == built.material.restitution


async def test_the_mesh_uri_is_carried_verbatim() -> None:
    built = await result()
    scene = build(job_id=JOB_ID, result=built, kind="tip", settings=SOLVER)
    assert scene.body.mesh.uri == built.mesh.uri
    assert scene.body.mesh.uri.startswith("gs://")


async def test_provenance_records_both_confidences_for_the_gate() -> None:
    built = await result()
    scene = build(job_id=JOB_ID, result=built, kind="tip", settings=SOLVER)
    assert scene.provenance is not None
    assert scene.provenance.source.value == "agent"
    assert scene.provenance.reconstruction_confidence == built.confidence.score
    assert scene.provenance.material_confidence == built.material.confidence


async def test_the_scene_validates_against_the_published_schema() -> None:
    """The physics service compiles this schema per route, so a scene that fails
    here would be a 400 in production rather than a simulation."""
    scene = build(job_id=JOB_ID, result=await result(), kind="tip", settings=SOLVER)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    body = scene.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert set(body.keys()) <= set(schema["properties"].keys())
    for required in schema["required"]:
        assert required in body
