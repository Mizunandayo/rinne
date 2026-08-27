"""A torchmcubes replacement built on scikit-image, plus the field-deviation capture.

WHY THIS FILE EXISTS
TripoSR's only non-PyPI dependency is `git+https://github.com/tatsy/torchmcubes.git`
- unpinnable, unhashable, no stated licence, and it compiles a CUDA extension,
which drags the entire ~3GB CUDA toolkit into the BUILD stage of an image that
otherwise does not need it. `skimage.measure.marching_cubes` does the same job
on the CPU in a few hundred milliseconds at TripoSR's grid size.

The shim is registered into ``sys.modules`` by :func:`install` BEFORE ``tsr`` is
imported, rather than by patching the vendored source. That distinction is the
whole point: the pinned TripoSR commit SHA stays a truthful integrity claim
because not one byte of the upstream tree is edited.

IT ALSO MEASURES SOMETHING. fieldDecisiveness needs to know how far the density
field sat from the iso-surface, and this function is the only place that sees
the field. Capturing it here is free; recomputing it later would mean keeping
the whole volume alive.

torch is imported LAZILY, inside the torch-facing entry point only. The Day 2
stub pipeline calls :func:`marching_cubes_numpy` directly and never touches
torch, so the default dependency set - and the CI job - stay torch-free.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray
from skimage import measure

#: Stride applied per axis when sampling the field. 4**3 == 64, i.e. the 1/64
#: sample the confidence spec calls for. Sampling rather than reducing keeps
#: the cost independent of grid resolution.
DEVIATION_STRIDE: Final = 4

MODULE_NAME: Final = "torchmcubes"

# Deviation arrays produced while a capture is active. A ContextVar rather than
# a module global so two concurrent requests - which --concurrency=1 forbids
# today but a raised flag would permit tomorrow - cannot read each other's field.
_capture: ContextVar[list[NDArray[np.float32]] | None] = ContextVar(
    "torchmcubes_capture", default=None
)


@dataclass(frozen=True)
class SurfaceExtraction:
    """One marching-cubes result plus the evidence for how decisive it was."""

    vertices: NDArray[np.float32]
    faces: NDArray[np.int64]
    #: |value - iso| over a 1/64 sample of the field, flattened.
    deviation: NDArray[np.float32]


def sample_deviation(field: NDArray[np.float32], iso: float) -> NDArray[np.float32]:
    """Absolute distance from the iso-surface over a strided sample of the field."""
    strided = field[::DEVIATION_STRIDE, ::DEVIATION_STRIDE, ::DEVIATION_STRIDE]
    return np.abs(strided.astype(np.float32, copy=False) - np.float32(iso)).ravel()


def marching_cubes_numpy(field: NDArray[np.float32], iso: float) -> SurfaceExtraction:
    """Extract an iso-surface and record how far the field sat from it.

    Returns an empty surface rather than raising when the iso-level does not
    cross the volume. A photograph that produces no surface is a low-confidence
    result, not a 500 - and the confidence floor is what expresses that.
    """
    volume = np.ascontiguousarray(field, dtype=np.float32)
    deviation = sample_deviation(volume, iso)

    active = _capture.get()
    if active is not None:
        active.append(deviation)

    try:
        vertices, faces, _normals, _values = measure.marching_cubes(volume, level=float(iso))
    except (ValueError, RuntimeError):
        # skimage raises when the level is outside the volume's range, or when
        # the surface is degenerate. Both mean "no surface", which is a real
        # answer about this field.
        return SurfaceExtraction(
            vertices=np.zeros((0, 3), dtype=np.float32),
            faces=np.zeros((0, 3), dtype=np.int64),
            deviation=deviation,
        )

    return SurfaceExtraction(
        vertices=np.asarray(vertices, dtype=np.float32),
        faces=np.asarray(faces, dtype=np.int64),
        deviation=deviation,
    )


@contextmanager
def capture_deviation() -> Iterator[list[NDArray[np.float32]]]:
    """Collect the deviation of every extraction performed inside the block.

    TripoSR calls marching cubes from inside its own code, so the caller never
    sees the field. This is how the confidence input gets out.
    """
    collected: list[NDArray[np.float32]] = []
    token = _capture.set(collected)
    try:
        yield collected
    finally:
        _capture.reset(token)


def to_torchmcubes_axis_order(vertices: NDArray[np.float32]) -> NDArray[np.float32]:
    """Reverse the vertex columns, because torchmcubes emits (z, y, x).

    ``mcubes_cpu.cpp`` iterates z over ``vol.size(0)`` and x over ``vol.size(2)``
    and then emits ``XYZ(x, y, z)``, so its output is the reverse of the array
    index order scikit-image returns. TripoSR's ``MarchingCubeHelper.forward``
    undoes that with ``v_pos[..., [2, 1, 0]]``; without this reversal that flip
    mirrors the mesh instead of correcting it.
    """
    return np.ascontiguousarray(vertices[:, ::-1], dtype=np.float32)


def marching_cubes(volume: Any, threshold: float) -> tuple[Any, Any]:
    """torchmcubes-compatible entry point: ``marching_cubes(vol, thresh)``.

    Accepts and returns torch tensors when handed one, so ``tsr`` cannot tell
    the difference. torch is imported here and nowhere else in this module.
    """
    if hasattr(volume, "detach"):  # a torch.Tensor, without importing torch to ask
        import torch

        field = volume.detach().to("cpu").numpy().astype(np.float32, copy=False)
        surface = marching_cubes_numpy(field, threshold)
        device = volume.device
        return (
            torch.from_numpy(to_torchmcubes_axis_order(surface.vertices)).to(device),
            torch.from_numpy(surface.faces.astype(np.int32, copy=False)).to(device),
        )

    surface = marching_cubes_numpy(np.asarray(volume, dtype=np.float32), threshold)
    return to_torchmcubes_axis_order(surface.vertices), surface.faces


def install(module_name: str = MODULE_NAME) -> types.ModuleType:
    """Register the shim in ``sys.modules`` so ``import torchmcubes`` resolves here.

    Idempotent, and it must run BEFORE the first ``import tsr``. Returns the
    module it registered so a test can assert on it.
    """
    existing = sys.modules.get(module_name)
    if existing is not None and getattr(existing, "__rinne_shim__", False):
        return existing

    module = types.ModuleType(module_name)
    module.__doc__ = "Rinne shim over skimage.measure.marching_cubes. Not the upstream package."
    module.__rinne_shim__ = True  # type: ignore[attr-defined]
    module.marching_cubes = marching_cubes  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    return module
