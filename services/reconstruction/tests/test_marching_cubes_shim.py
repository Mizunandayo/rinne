from __future__ import annotations

import sys

import numpy as np

from rinne_reconstruction.vendor_shims import torchmcubes_shim as shim


def _sphere_field(resolution: int = 32) -> np.ndarray:
    axis = np.linspace(-2.0, 2.0, resolution, dtype=np.float32)
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    return np.sqrt(x * x + y * y + z * z).astype(np.float32)


def test_it_extracts_a_surface_without_torch_or_a_cuda_extension() -> None:
    """The whole reason this file exists.

    torchmcubes has no PyPI release, no pin, no stated licence, and it compiles
    a CUDA extension that drags the full toolkit into the build stage. This
    produces the same surface from scikit-image, on the CPU, from a dependency
    set that does not contain torch at all.
    """
    assert "torch" not in sys.modules

    surface = shim.marching_cubes_numpy(_sphere_field(), 1.0)

    assert surface.vertices.shape[1] == 3
    assert surface.faces.shape[1] == 3
    assert surface.faces.shape[0] > 100
    assert "torch" not in sys.modules


def test_the_deviation_sample_is_one_voxel_in_sixty_four() -> None:
    resolution = 32
    surface = shim.marching_cubes_numpy(_sphere_field(resolution), 1.0)
    expected = (resolution // shim.DEVIATION_STRIDE) ** 3
    assert surface.deviation.shape == (expected,)
    assert expected * 64 == resolution**3
    assert np.all(surface.deviation >= 0.0)


def test_the_deviation_is_the_distance_from_the_iso_level() -> None:
    field = np.full((8, 8, 8), 3.0, dtype=np.float32)
    assert np.allclose(shim.sample_deviation(field, 1.0), 2.0)


def test_an_iso_level_outside_the_volume_is_an_empty_surface_not_an_exception() -> None:
    """A photograph that produces no surface is a low-confidence result.

    Raising here would turn it into a 500. Returning nothing lets the
    confidence floor express it, which is the honest answer.
    """
    surface = shim.marching_cubes_numpy(_sphere_field(), 999.0)
    assert surface.vertices.shape == (0, 3)
    assert surface.faces.shape == (0, 3)
    assert surface.deviation.size > 0


def test_capture_collects_the_field_from_inside_a_call_it_cannot_see() -> None:
    """TripoSR calls marching cubes internally, so this is the only way out."""
    with shim.capture_deviation() as collected:
        shim.marching_cubes_numpy(_sphere_field(), 1.0)
        shim.marching_cubes_numpy(_sphere_field(), 1.5)
    assert len(collected) == 2

    # Outside the block nothing is retained, so one request cannot read
    # another's field.
    with shim.capture_deviation() as second:
        pass
    assert second == []


def test_install_registers_the_shim_and_is_idempotent() -> None:
    name = "torchmcubes_probe"
    try:
        first = shim.install(name)
        assert sys.modules[name] is first
        assert first.marching_cubes is shim.marching_cubes
        # Registering in sys.modules rather than patching the vendored TripoSR
        assert shim.install(name) is first
    finally:
        sys.modules.pop(name, None)


def test_the_torch_facing_entry_point_accepts_a_plain_array() -> None:
    vertices, faces = shim.marching_cubes(_sphere_field(), 1.0)
    assert isinstance(vertices, np.ndarray)
    assert isinstance(faces, np.ndarray)
    assert faces.shape[0] > 100
