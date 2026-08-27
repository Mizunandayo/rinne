"""Mesh normalisation, measurement, and GLB export.

Normalisation is a fixed pipeline, and the ORDER is load-bearing:

  1. ``process=True`` merges duplicate vertices and drops degenerate faces.
     Marching cubes produces both, and either one alone makes ``is_watertight``
     report False on a genuinely closed surface - which would then be measured
     as a low watertightness score and reported as low confidence. The number
     would be wrong, not just ugly.
  2. ``remove_unreferenced_vertices`` - the merge in step 1 orphans some.
  3. ``repair.fix_normals`` - marching cubes does not guarantee consistent
     winding, and signed volume is meaningless until it does.
  4. Z-up to Y-up. Marching cubes indexes the volume, so its up axis is Z; glTF
     and the Rapier scene are both Y-up. Rotating once here means no consumer
     has to guess, which is why the contract carries ``upAxis`` at all.
  5. Seat on the ground plane and centre in XZ, so a physics scene can drop
     the body at a known translation.
  6. Scale so the longest bounding-box edge equals the assumed dimension, then
     re-seat, because scaling about the origin moves the floor contact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import trimesh
from numpy.typing import NDArray

#: Below this, a "mesh" is noise. Kept here rather than in config because it is
#: a property of the export format, not an operational choice.
_MIN_EXPORTABLE_FACES: Final = 4


@dataclass(frozen=True)
class MeshMeasurements:
    """Everything the contract reports about the normalised mesh."""

    vertex_count: int
    face_count: int
    watertight: bool
    extent: tuple[float, float, float]
    volume_cubic_meters: float
    boundary_edge_ratio: float


class MeshNormalisationError(ValueError):
    """The surface could not be turned into an exportable mesh."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


def normalise(
    vertices: NDArray[np.float32],
    faces: NDArray[np.int64],
    *,
    vertex_colors: NDArray[np.uint8] | None,
    longest_dimension_meters: float,
) -> trimesh.Trimesh:
    """Turn a raw marching-cubes surface into a metre-scaled, Y-up, seated mesh."""
    if faces.shape[0] < _MIN_EXPORTABLE_FACES:
        raise MeshNormalisationError("reconstruction produced no usable surface")

    mesh = trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=np.float64),
        faces=np.asarray(faces, dtype=np.int64),
        vertex_colors=vertex_colors,
        process=True,
    )
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(mesh)

    if mesh.faces.shape[0] < _MIN_EXPORTABLE_FACES:
        raise MeshNormalisationError("reconstruction produced no usable surface")

    # Z-up to Y-up: -90 degrees about X.
    mesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2.0, (1.0, 0.0, 0.0)))

    _seat(mesh)

    longest_edge = float(np.max(mesh.extents))
    if longest_edge <= 0.0:
        raise MeshNormalisationError("reconstruction produced a degenerate bounding box")
    mesh.apply_scale(longest_dimension_meters / longest_edge)

    # Scaling is about the origin, so the ground contact moved. Seat again.
    _seat(mesh)
    return mesh


def _seat(mesh: trimesh.Trimesh) -> None:
    """Lowest point to y=0, XZ centroid to the origin."""
    lower, upper = mesh.bounds
    mesh.apply_translation(
        (
            -(lower[0] + upper[0]) / 2.0,
            -lower[1],
            -(lower[2] + upper[2]) / 2.0,
        )
    )


def measure(mesh: trimesh.Trimesh) -> MeshMeasurements:
    """Read the properties the contract reports, after normalisation."""
    extents = np.asarray(mesh.extents, dtype=np.float64)
    return MeshMeasurements(
        vertex_count=int(mesh.vertices.shape[0]),
        face_count=int(mesh.faces.shape[0]),
        watertight=bool(mesh.is_watertight),
        extent=(float(extents[0]), float(extents[1]), float(extents[2])),
        volume_cubic_meters=abs(float(mesh.volume)),
        boundary_edge_ratio=boundary_edge_ratio(mesh),
    )


def boundary_edge_ratio(mesh: trimesh.Trimesh) -> float:
    """Share of edges belonging to exactly one face.

    A closed surface has none. Counting them is how a mesh that is *nearly*
    closed scores better than one with a hole through it, instead of both
    collapsing to "not watertight".
    """
    edges = np.asarray(mesh.edges_sorted)
    if edges.shape[0] == 0:
        return 1.0
    _unique, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = int(np.count_nonzero(counts == 1))
    total = int(counts.shape[0])
    return boundary / total if total else 1.0


def mean_vertex_color(mesh: trimesh.Trimesh) -> tuple[float, float, float] | None:
    """Mean RGB of the vertex colours, 0-255, or None when the mesh has none."""
    visual = getattr(mesh, "visual", None)
    colors = getattr(visual, "vertex_colors", None)
    if colors is None:
        return None
    array = np.asarray(colors, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] < 3:
        return None
    mean = array[:, :3].mean(axis=0)
    return (float(mean[0]), float(mean[1]), float(mean[2]))


def export_glb(mesh: trimesh.Trimesh) -> bytes:
    """Serialise to a binary glTF, which is what the contract's format enum says."""
    data = trimesh.Trimesh.export(mesh, file_type="glb")
    if isinstance(data, str):  # defensive: some exporters return text
        return data.encode("utf-8")
    return bytes(data)
