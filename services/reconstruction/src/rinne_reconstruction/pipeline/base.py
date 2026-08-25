"""The reconstructor interface. One method, so the stub and TripoSR are swappable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray
from PIL import Image

PipelineName = Literal["stub", "triposr"]
Device = Literal["cpu", "cuda"]


@dataclass(frozen=True)
class RawReconstruction:
    """A surface straight out of marching cubes, before any normalisation."""

    vertices: NDArray[np.float32]
    faces: NDArray[np.int64]
    vertex_colors: NDArray[np.uint8] | None
    deviation: NDArray[np.float32]
    seed: int


@runtime_checkable
class Reconstructor(Protocol):
    """What the route requires of a reconstructor. Synchronous and CPU-blocking."""

    @property
    def name(self) -> PipelineName: ...

    @property
    def version(self) -> str: ...

    @property
    def device(self) -> Device: ...

    def reconstruct(self, image: Image.Image) -> RawReconstruction: ...
