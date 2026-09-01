"""TRELLIS.2: a sparse-voxel model that returns PBR materials, not vertex colour.

It differs from the other two pipelines in what it hands back. TripoSR and
InstantMesh produce a bare surface that this service then colours, scales and
measures. TRELLIS.2 produces a FINISHED asset - remeshed, UV-unwrapped, with a
4K texture - and the job here is to take it apart carefully enough that the rest
of the service still works on it: normalise still scales and seats it, measure
still reports a closed surface, and the confidence gate still has its inputs.

Watertightness is why `measure` welds before testing. UV mapping splits vertices
at every chart seam, so a textured asset reads as open even when the surface it
describes is closed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from PIL import Image

from rinne_reconstruction.imaging.segmentation import U2netpSegmenter, crop_and_composite
from rinne_reconstruction.pipeline.base import Device, PipelineName, RawReconstruction

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

#: The model's own normalised box. Vertices come back inside it, and normalise
#: rescales to metres afterwards exactly as it does for the other pipelines.
_AABB: Final = [[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]]
_WHITE: Final = 1.0


class Trellis2Reconstructor:
    """One pipeline, resident. 4B parameters is most of an L4's memory."""

    def __init__(
        self,
        *,
        pipeline: Any,
        segmenter: U2netpSegmenter,
        device: Device,
        version: str,
        foreground_ratio: float,
        texture_size: int,
        decimation_target: int,
        remesh: bool,
    ) -> None:
        self._pipeline = pipeline
        self._segmenter = segmenter
        self._device: Device = device
        self._version = version
        self._foreground_ratio = foreground_ratio
        self._texture_size = texture_size
        self._decimation_target = decimation_target
        self._remesh = remesh

    @property
    def name(self) -> PipelineName:
        return "trellis2"

    @property
    def version(self) -> str:
        return self._version

    @property
    def device(self) -> Device:
        return self._device

    def reconstruct(
        self,
        image: Image.Image,
        *,
        label: str | None = None,
        views: list[Image.Image] | None = None,
    ) -> RawReconstruction:
        # TRELLIS.2 takes one image and has no text or multi-view input.
        del label, views
        import o_voxel
        import torch

        found = self._segmenter.segment(image)
        framed = crop_and_composite(
            image, found.mask, foreground_ratio=self._foreground_ratio, background=_WHITE
        )

        seed = _seed_from(framed)
        torch.manual_seed(seed)

        with torch.no_grad():
            mesh = self._pipeline.run(framed)[0]

        # to_glb does the remesh, the unwrap and the texture bake in one pass.
        asset = o_voxel.postprocess.to_glb(
            vertices=mesh.vertices,
            faces=mesh.faces,
            attr_volume=mesh.attrs,
            coords=mesh.coords,
            attr_layout=mesh.layout,
            voxel_size=mesh.voxel_size,
            aabb=_AABB,
            decimation_target=self._decimation_target,
            texture_size=self._texture_size,
            remesh=self._remesh,
        )

        vertices, faces, uv, texture = _unpack(asset)
        logger.info(
            "trellis2 reconstructed",
            extra={"faces": int(faces.shape[0]), "textured": texture is not None},
        )
        return RawReconstruction(
            vertices=vertices,
            faces=faces,
            vertex_colors=None,
            # The model reports no per-sample density, so there is nothing honest
            # to put here. field_decisiveness is scored from it and an empty array
            # reads as zero, so the weights are rescaled instead - see the route.
            deviation=np.zeros(0, dtype=np.float32),
            seed=seed,
            foreground=found.measurements,
            uv=uv,
            texture=texture,
        )


def build_trellis2_reconstructor(
    *,
    weights_dir: str,
    segmentation_model_path: str,
    version: str,
    foreground_ratio: float,
    texture_size: int,
    decimation_target: int,
    remesh: bool,
) -> Trellis2Reconstructor:
    """Load the pipeline. Called from the lifespan, before the port answers."""
    import torch
    from trellis2.pipelines import Trellis2ImageTo3DPipeline

    pipeline = Trellis2ImageTo3DPipeline.from_pretrained(weights_dir)
    device: Device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        pipeline.cuda()

    return Trellis2Reconstructor(
        pipeline=pipeline,
        segmenter=U2netpSegmenter(segmentation_model_path),
        device=device,
        version=version,
        foreground_ratio=foreground_ratio,
        texture_size=texture_size,
        decimation_target=decimation_target,
        remesh=remesh,
    )


def _unpack(
    asset: Any,
) -> tuple[NDArray[np.float32], NDArray[np.int64], NDArray[np.float32] | None, Image.Image | None]:
    """Take the finished asset apart into what RawReconstruction carries.

    `to_glb` returns a trimesh Scene or Trimesh depending on the build, so this
    accepts either rather than assuming one and failing on the other.
    """
    import trimesh

    geometry = asset
    if isinstance(asset, trimesh.Scene):
        meshes = [g for g in asset.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("trellis2 returned a scene with no mesh")
        geometry = meshes[0] if len(meshes) == 1 else trimesh.util.concatenate(meshes)

    vertices = np.ascontiguousarray(geometry.vertices, dtype=np.float32)
    faces = np.ascontiguousarray(geometry.faces, dtype=np.int64)

    visual = getattr(geometry, "visual", None)
    uv = getattr(visual, "uv", None)
    material = getattr(visual, "material", None)
    texture = getattr(material, "baseColorTexture", None)

    if uv is None or texture is None:
        return vertices, faces, None, None
    return (
        vertices,
        faces,
        np.ascontiguousarray(uv, dtype=np.float32),
        texture.convert("RGB") if texture.mode != "RGB" else texture,
    )


def _seed_from(image: Image.Image) -> int:
    """Same rule as the other pipelines: the seed is a property of the bytes."""
    import hashlib

    return int.from_bytes(hashlib.sha256(image.tobytes()).digest()[:4], "big")
