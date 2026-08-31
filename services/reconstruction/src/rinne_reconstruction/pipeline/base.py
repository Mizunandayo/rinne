"""The reconstructor interface. one method, so the stub and triposr are swappable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray
from PIL import Image

if TYPE_CHECKING:
    from PIL.Image import Image as PillowImage

PipelineName = Literal["stub", "triposr", "instantmesh"]
Device = Literal["cpu", "cuda"]


@dataclass(frozen=True)
class ForegroundMeasurements:
    """What the segmentation mask says about how the object was photographed.

    Lives here rather than in imaging/ because it is a field of the pipeline's
    own output, and a pipeline that does not segment reports None instead.
    """

    coverage: float
    border_fraction: float


@dataclass(frozen=True)
class RawReconstruction:
    """A surface straight out of marching cubes, before any normalisation."""

    vertices: NDArray[np.float32]
    faces: NDArray[np.int64]
    vertex_colors: NDArray[np.uint8] | None
    deviation: NDArray[np.float32]
    seed: int
    foreground: ForegroundMeasurements | None = None
    #: Set only when the pipeline baked an atlas. Colour then comes from the
    #: texture rather than from one sample per vertex, and `vertex_colors` is
    #: left unused rather than being a second, disagreeing source.
    uv: NDArray[np.float32] | None = None
    texture: PillowImage | None = None


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
