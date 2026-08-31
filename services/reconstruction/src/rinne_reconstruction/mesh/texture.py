"""Bake a UV texture on the CPU, so colour is not limited to one sample per vertex.

InstantMesh's own `xatlas_uvmap` uses nvdiffrast to rasterise, which JIT-compiles
CUDA kernels on first use and needs a toolchain the runtime image does not carry.
The rasterisation itself is barycentric interpolation over triangles, which numpy
does perfectly well, so this does that instead and keeps the container unchanged.

The gain is real: a 1024 square atlas is a million texels against roughly a
hundred thousand vertices, and the colour source can be queried at any point.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from PIL import Image

logger = logging.getLogger(__name__)

#: Texels outside every triangle keep this, so a seam reads as background rather
#: than as black fringing when the GPU samples across a chart edge.
_FILL: Final = np.array([127, 127, 127], dtype=np.uint8)
_MIN_TEXTURE_FACES: Final = 16

SampleColors = Callable[[NDArray[np.float32]], NDArray[np.float32]]


class TextureBakeError(RuntimeError):
    """Baking failed. The caller falls back to vertex colour rather than failing."""


@dataclass(frozen=True)
class BakedTexture:
    """A re-indexed surface plus its atlas. The vertices are still in the space
    they were sampled in, because normalisation happens after this, not before."""

    vertices: NDArray[np.float32]
    faces: NDArray[np.int64]
    uv: NDArray[np.float32]
    image: Image.Image


def bake(
    vertices_in: NDArray[np.float32],
    faces_in: NDArray[np.int64],
    *,
    sample: SampleColors,
    resolution: int,
) -> BakedTexture:
    """Unwrap, rasterise, and sample colour per texel. Raises on any failure so
    the caller can fall back to vertex colour rather than ship a broken surface.

    IMPORTANT: the vertices must be in the same space the sampler expects. The
    colour source is the density field, which lives in the triplane's own [-1, 1]
    box, so this runs BEFORE the mesh is scaled to metres and turned Y-up.
    """
    import xatlas

    if faces_in.shape[0] < _MIN_TEXTURE_FACES:
        raise TextureBakeError("too few faces to unwrap")

    vertices = np.asarray(vertices_in, dtype=np.float32)
    faces = np.asarray(faces_in, dtype=np.uint32)
    mapping, indices, uvs = xatlas.parametrize(vertices, faces)

    uv = np.asarray(uvs, dtype=np.float32)
    tri = np.asarray(indices, dtype=np.int64)
    source = np.asarray(mapping, dtype=np.int64)
    if uv.shape[0] == 0 or tri.shape[0] == 0:
        raise TextureBakeError("the unwrap produced no charts")

    # Texel centres, and v flipped because image rows run down while UV runs up.
    pixels = np.full((resolution, resolution, 3), _FILL, dtype=np.uint8)
    corners = uv[tri] * (resolution - 1)
    corners[..., 1] = (resolution - 1) - corners[..., 1]
    world = vertices[source][tri]

    points: list[NDArray[np.float32]] = []
    rows: list[NDArray[np.int64]] = []
    cols: list[NDArray[np.int64]] = []

    for index in range(tri.shape[0]):
        uvw = corners[index]
        lo = np.floor(uvw.min(axis=0)).astype(np.int64)
        hi = np.ceil(uvw.max(axis=0)).astype(np.int64)
        x0, y0 = max(int(lo[0]), 0), max(int(lo[1]), 0)
        x1, y1 = min(int(hi[0]) + 1, resolution), min(int(hi[1]) + 1, resolution)
        if x1 <= x0 or y1 <= y0:
            continue

        gx, gy = np.meshgrid(np.arange(x0, x1), np.arange(y0, y1), indexing="xy")
        px = gx.astype(np.float32) + 0.5
        py = gy.astype(np.float32) + 0.5

        ax, ay = uvw[0]
        bx, by = uvw[1]
        cx, cy = uvw[2]
        denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(denominator) < 1e-12:
            continue

        w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denominator
        w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denominator
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not inside.any():
            continue

        a, b, c = world[index]
        position = (
            w0[inside][:, None] * a + w1[inside][:, None] * b + w2[inside][:, None] * c
        ).astype(np.float32)
        points.append(position)
        rows.append(gy[inside].astype(np.int64))
        cols.append(gx[inside].astype(np.int64))

    if not points:
        raise TextureBakeError("no texel fell inside a chart")

    colors = sample(np.concatenate(points, axis=0))
    if colors.shape[0] != sum(part.shape[0] for part in points):
        raise TextureBakeError("the colour sampler returned the wrong number of values")

    pixels[np.concatenate(rows), np.concatenate(cols)] = np.clip(colors * 255.0, 0, 255).astype(
        np.uint8
    )

    logger.info("texture baked", extra={"resolution": resolution, "faces": int(tri.shape[0])})
    return BakedTexture(
        vertices=np.ascontiguousarray(vertices[source], dtype=np.float32),
        faces=np.ascontiguousarray(tri, dtype=np.int64),
        uv=np.ascontiguousarray(uv, dtype=np.float32),
        image=Image.fromarray(pixels, mode="RGB"),
    )
