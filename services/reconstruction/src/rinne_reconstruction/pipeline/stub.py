"""The stub reconstructor: a real pipeline that produces a placeholder shape.

WHAT IS FAKE HERE, PRECISELY: the geometry. A superellipsoid is fitted to the
photograph's aspect ratio and colouring, not to the object in it.

WHAT IS REAL: everything else. There is a genuine density field, it goes
through the same marching-cubes shim TripoSR will use, so fieldDecisiveness is
measured rather than invented. The surface is normalised, measured, coloured
from the actual photograph, exported as a real GLB and uploaded to real
storage. Every field in ReconstructionResult is populated by something that
happened.

That is why ``pipeline.name`` exists in the contract. The payload says "stub",
so nothing downstream - and nobody watching a demo - has to take anybody's word
for which pipeline ran.

It is also deliberately CPU-only: ``device`` reports "cpu" because that is the
truth. The L4 is attached to the instance; this pipeline does not use it. Day 3
swaps in TripoSR and the same field starts reporting "cuda" for the same reason.
"""

from __future__ import annotations

import hashlib
from typing import Final

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from rinne_reconstruction.pipeline.base import Device, PipelineName, RawReconstruction
from rinne_reconstruction.vendor_shims.torchmcubes_shim import marching_cubes_numpy

#: The field is sampled over [-EXTENT, EXTENT] on each axis so the surface is
#: comfortably inside the volume and never clipped by the boundary - a clipped
#: surface is not watertight, and that would be a measurement of this function
#: rather than of the reconstruction.
_EXTENT: Final = 1.35

#: The field is an OCCUPANCY field cut at zero, not a distance field cut at its
#: skin. That distinction is not cosmetic.
_ISO: Final = 0.0
_SHARPNESS: Final = 6.0

#: Superellipsoid exponent range. 2 is an ellipsoid, 6 is nearly a rounded box.
_EXPONENT_MIN: Final = 2.0
_EXPONENT_MAX: Final = 6.0

#: Image is reduced to this before colour sampling. Enough for a mean and a
#: coarse projection, small enough to be free.
_COLOR_SAMPLE_EDGE: Final = 64


class StubReconstructor:
    """Deterministic placeholder geometry, honest instrumentation."""

    def __init__(self, *, resolution: int = 64) -> None:
        self._resolution = resolution

    @property
    def name(self) -> PipelineName:
        return "stub"

    @property
    def version(self) -> str:
        return f"stub-1-r{self._resolution}"

    @property
    def device(self) -> Device:
        return "cpu"

    def reconstruct(self, image: Image.Image) -> RawReconstruction:
        seed = _seed_from(image)
        width, height = image.size

        # Aspect drives the proportions: a tall photograph produces a tall
        # object. Axis 2 is up in field space and becomes Y after the Z-up to
        # Y-up rotation in mesh.normalise.
        longest = float(max(width, height))
        half_x = 0.55 + 0.35 * (width / longest)
        half_z = 0.55 + 0.35 * (height / longest)
        half_y = 0.55 + 0.35 * ((width + height) / (2.0 * longest))

        # One seeded degree of freedom, so two different photographs of similar
        # proportions do not produce a pixel-identical blob.
        exponent = _EXPONENT_MIN + (_EXPONENT_MAX - _EXPONENT_MIN) * ((seed % 1000) / 1000.0)

        field = _superellipsoid_field(
            resolution=self._resolution,
            half_extents=(half_x, half_y, half_z),
            exponent=exponent,
        )

        surface = marching_cubes_numpy(field, _ISO)
        colors = _sample_colors(image, surface.vertices, self._resolution)

        return RawReconstruction(
            vertices=surface.vertices,
            faces=surface.faces,
            vertex_colors=colors,
            deviation=surface.deviation,
            seed=seed,
        )


def _seed_from(image: Image.Image) -> int:
    """Stable 32-bit seed over the decoded pixels.

    Over pixels rather than over the uploaded file: the service re-encodes
    every image, so two uploads of the same photograph in different containers
    must produce the same mesh, and the same requestId must be reproducible.
    """
    digest = hashlib.blake2b(image.tobytes(), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def _superellipsoid_field(
    *,
    resolution: int,
    half_extents: tuple[float, float, float],
    exponent: float,
) -> NDArray[np.float32]:
    """Sample a superellipsoid occupancy field on a cubic grid.

    ``(|x/a|^e + |y/b|^e + |z/c|^e)^(1/e)`` is 1.0 on the skin; tanh turns that
    into an occupancy field that is close to +1 well inside, close to -1 well
    outside, and crosses zero in a thin shell. See _SHARPNESS for why the shape
    of the field matters as much as the shape of the object.
    """
    axis = np.linspace(-_EXTENT, _EXTENT, resolution, dtype=np.float32)
    grid_x, grid_y, grid_z = np.meshgrid(axis, axis, axis, indexing="ij")

    half_x, half_y, half_z = half_extents
    powered = (
        np.abs(grid_x / np.float32(half_x)) ** exponent
        + np.abs(grid_y / np.float32(half_y)) ** exponent
        + np.abs(grid_z / np.float32(half_z)) ** exponent
    )
    distance = powered ** (1.0 / exponent)
    # Positive inside, negative outside, saturating quickly on both sides.
    return np.asarray(np.tanh(_SHARPNESS * (1.0 - distance)), dtype=np.float32)


def _sample_colors(
    image: Image.Image,
    vertices: NDArray[np.float32],
    resolution: int,
) -> NDArray[np.uint8] | None:
    """Project each vertex onto the photograph and take that pixel's colour.

    This is what gives mesh.material a real signal: the mean vertex colour is
    the mean colour of the object as photographed, not a flat fill chosen here.
    """
    if vertices.shape[0] == 0:
        return None

    thumbnail = image.convert("RGB").resize(
        (_COLOR_SAMPLE_EDGE, _COLOR_SAMPLE_EDGE), Image.Resampling.BILINEAR
    )
    pixels = np.asarray(thumbnail, dtype=np.uint8)

    # Marching cubes returns vertices in VOLUME INDEX space, 0..resolution-1.
    span = max(resolution - 1, 1)
    columns = np.clip(
        (vertices[:, 0] / span * (_COLOR_SAMPLE_EDGE - 1)).astype(np.int64),
        0,
        _COLOR_SAMPLE_EDGE - 1,
    )
    # Axis 2 is up in field space and row 0 of an image is the top, so the row
    # index is inverted. Without this the object is lit upside down.
    rows = np.clip(
        ((span - vertices[:, 2]) / span * (_COLOR_SAMPLE_EDGE - 1)).astype(np.int64),
        0,
        _COLOR_SAMPLE_EDGE - 1,
    )

    rgb = pixels[rows, columns]
    alpha = np.full((rgb.shape[0], 1), 255, dtype=np.uint8)
    return np.asarray(np.hstack((rgb, alpha)), dtype=np.uint8)
