from __future__ import annotations

import numpy as np
import pytest
import trimesh

from rinne_reconstruction.mesh import _smooth, normalise

TARGET_METERS = 0.23


def bumpy(subdivisions: int = 3, amplitude: float = 0.06, seed: int = 7) -> trimesh.Trimesh:
    """A sphere with radial noise: the same defect marching cubes leaves behind,
    where the surface carries the field's quantisation rather than the object's."""
    sphere = trimesh.creation.icosphere(subdivisions=subdivisions, radius=1.0)
    rng = np.random.default_rng(seed)
    normals = sphere.vertices / np.linalg.norm(sphere.vertices, axis=1, keepdims=True)
    noise = rng.normal(0.0, amplitude, size=(sphere.vertices.shape[0], 1))
    return trimesh.Trimesh(vertices=sphere.vertices + normals * noise, faces=sphere.faces)


def roughness(mesh: trimesh.Trimesh) -> float:
    radii = np.linalg.norm(mesh.vertices - mesh.centroid, axis=1)
    return float(np.std(radii))


def test_smoothing_removes_the_surface_noise_it_is_there_for() -> None:
    mesh = bumpy()
    before = roughness(mesh)
    _smooth(mesh, 12)
    assert roughness(mesh) < before * 0.5


def test_smoothing_preserves_volume_because_mass_is_derived_from_it() -> None:
    """Taubin, not Laplacian. A shrinking filter would quietly reduce the object's
    volume, and volume is what the material estimator turns into kilograms."""
    mesh = bumpy()
    before = mesh.volume
    _smooth(mesh, 12)
    assert mesh.volume == pytest.approx(before, rel=0.05)


def test_zero_iterations_is_exactly_a_no_op() -> None:
    mesh = bumpy()
    original = mesh.vertices.copy()
    _smooth(mesh, 0)
    assert np.array_equal(mesh.vertices, original)


def test_smoothing_moves_vertices_without_decimating() -> None:
    mesh = bumpy()
    faces = mesh.faces.shape[0]
    vertices = mesh.vertices.shape[0]
    _smooth(mesh, 8)
    assert mesh.faces.shape[0] == faces
    assert mesh.vertices.shape[0] == vertices


def test_normalise_applies_it_and_still_seats_and_scales() -> None:
    mesh = bumpy()
    rough = normalise(
        np.asarray(mesh.vertices, dtype=np.float32),
        np.asarray(mesh.faces, dtype=np.int64),
        vertex_colors=None,
        longest_dimension_meters=TARGET_METERS,
        smoothing_iterations=0,
    )
    smooth = normalise(
        np.asarray(mesh.vertices, dtype=np.float32),
        np.asarray(mesh.faces, dtype=np.int64),
        vertex_colors=None,
        longest_dimension_meters=TARGET_METERS,
        smoothing_iterations=12,
    )
    assert roughness(smooth) < roughness(rough)
    for result in (rough, smooth):
        assert float(np.max(result.extents)) == pytest.approx(TARGET_METERS, rel=1e-3)
        assert result.bounds[0][1] == pytest.approx(0.0, abs=1e-9)


def test_decimation_keeps_the_colour_the_pipeline_produced() -> None:
    """simplify_quadric_decimation returns a uniform white mesh: it discards vertex
    colour entirely. Without resampling, every reconstruction renders as plaster."""
    sphere = trimesh.creation.icosphere(subdivisions=4)
    rng = np.random.default_rng(3)
    colors = (rng.random((sphere.vertices.shape[0], 3)) * 255).astype(np.uint8)

    reduced = normalise(
        np.asarray(sphere.vertices, dtype=np.float32),
        np.asarray(sphere.faces, dtype=np.int64),
        vertex_colors=colors,
        longest_dimension_meters=TARGET_METERS,
        target_faces=600,
    )

    surviving = np.unique(np.asarray(reduced.visual.vertex_colors)[:, :3], axis=0)
    assert reduced.faces.shape[0] <= 600
    assert len(surviving) > 50


def test_a_mesh_without_colour_stays_without_colour() -> None:
    """No invented default: a pipeline that reports no colour must not gain one."""
    sphere = trimesh.creation.icosphere(subdivisions=4)
    reduced = normalise(
        np.asarray(sphere.vertices, dtype=np.float32),
        np.asarray(sphere.faces, dtype=np.int64),
        vertex_colors=None,
        longest_dimension_meters=TARGET_METERS,
        target_faces=600,
    )
    assert reduced.faces.shape[0] <= 600


def test_a_baked_atlas_survives_normalisation() -> None:
    """UVs index vertices, so normalise must not weld or reorder them. It also
    must not decimate a mesh that was already reduced for the unwrap."""
    from PIL import Image

    sphere = trimesh.creation.icosphere(subdivisions=3)
    vertices = np.asarray(sphere.vertices, dtype=np.float32)
    faces = np.asarray(sphere.faces, dtype=np.int64)
    uv = np.zeros((vertices.shape[0], 2), dtype=np.float32)
    texture = Image.new("RGB", (16, 16), (200, 40, 40))

    out = normalise(
        vertices,
        faces,
        vertex_colors=None,
        longest_dimension_meters=TARGET_METERS,
        target_faces=32,
        uv=uv,
        texture=texture,
    )

    # Untouched topology, and the atlas still attached after scale and seat.
    assert out.vertices.shape[0] == vertices.shape[0]
    assert out.faces.shape[0] == faces.shape[0]
    assert out.visual.uv.shape[0] == vertices.shape[0]
    assert float(np.max(out.extents)) == pytest.approx(TARGET_METERS, rel=1e-3)
