"""The real reconstructor: TripoSR, vendored at a pinned commit, run on the l4"""

from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from rinne_reconstruction.imaging.segmentation import U2netpSegmenter, crop_and_composite
from rinne_reconstruction.pipeline.base import Device, PipelineName, RawReconstruction
from rinne_reconstruction.vendor_shims import torchmcubes_shim

# imported at module scope
_UNUSED_UPSTREAM_MODULES: Final[tuple[str, ...]] = ("rembg", "imageio")

_CONFIG_NAME: Final = "config.yaml"
_WEIGHT_NAME: Final = "model.ckpt"


class TripoSRReconstructor:
    """One loaded TSR model plus one laoded u2netp session, reused per request."""

    def __init__(
        self,
        *,
        model: Any,
        segmenter: U2netpSegmenter,
        device: Device,
        commit_sha: str,
        marching_cubes_resolution: int,
        foreground_ratio: float,
    ) -> None:
        self._model = model
        self._segmenter = segmenter
        self._device = device
        self._commit_sha = commit_sha
        self._resolution = marching_cubes_resolution
        self._foreground_ratio = foreground_ratio

    @property
    def name(self) -> PipelineName:
        return "triposr"

    @property
    def version(self) -> str:
        return self._commit_sha

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
        # TripoSR is DINO into a triplane transformer. There is no text input
        # to condition, so a label cannot reach it.
        del label, views
        import torch

        foreground = self._segmenter.segment(image)
        framed = crop_and_composite(image, foreground.mask, foreground_ratio=self._foreground_ratio)

        seed = _seed_from(framed)
        torch.manual_seed(seed)

        with torch.no_grad():
            scene_codes = self._model([framed], device=self._device)
            with torchmcubes_shim.capture_deviation() as captured:
                meshes = self._model.extract_mesh(scene_codes, True, resolution=self._resolution)

        mesh = meshes[0]
        deviation = np.concatenate(captured) if captured else np.zeros(0, dtype=np.float32)

        return RawReconstruction(
            vertices=np.asarray(mesh.vertices, dtype=np.float32),
            faces=np.asarray(mesh.faces, dtype=np.int64),
            vertex_colors=_vertex_colors(mesh),
            deviation=np.asarray(deviation, dtype=np.float32),
            seed=seed,
            foreground=foreground.measurements,
        )


def build_triposr_reconstructor(
    *,
    source_dir: str,
    weights_dir: str,
    segmentation_model_path: str,
    commit_sha: str,
    marching_cubes_resolution: int,
    chunk_size: int,
    foreground_ratio: float,
) -> TripoSRReconstructor:
    """Load the model. Called from the lifespan block, before the port answers."""
    import torch

    _install_upstream_stubs()
    torchmcubes_shim.install()

    source = Path(source_dir)
    if not (source / "tsr" / "system.py").is_file():
        raise FileNotFoundError(f"vendored TripoSR source not found at {source}")
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

    weights = Path(weights_dir)
    for required in (_CONFIG_NAME, _WEIGHT_NAME):
        if not (weights / required).is_file():
            raise FileNotFoundError(f"TripoSR {required} not found in {weights}")

    from tsr.system import TSR

    model = TSR.from_pretrained(str(weights), config_name=_CONFIG_NAME, weight_name=_WEIGHT_NAME)
    model.renderer.set_chunk_size(chunk_size)
    model.eval()

    device: Device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    return TripoSRReconstructor(
        model=model,
        segmenter=U2netpSegmenter(segmentation_model_path),
        device=device,
        commit_sha=commit_sha,
        marching_cubes_resolution=marching_cubes_resolution,
        foreground_ratio=foreground_ratio,
    )


def _install_upstream_stubs() -> None:
    """Register empty modules for the two upstream imports this path never calls."""
    for module_name in _UNUSED_UPSTREAM_MODULES:
        if module_name in sys.modules:
            continue
        module = types.ModuleType(module_name)
        module.__doc__ = "Rinne stub. Imported by tsr/utils.py, never called by this service."
        module.__rinne_stub__ = True  # type: ignore[attr-defined]
        sys.modules[module_name] = module


def _seed_from(image: Image.Image) -> int:
    """Stable 32-bit seed over the pixels the model is about to see."""
    digest = hashlib.blake2b(image.tobytes(), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def _vertex_colors(mesh: Any) -> NDArray[np.uint8] | None:
    """RGBA per vertex, or None when the extraction produced no colour."""
    visual = getattr(mesh, "visual", None)
    colors = getattr(visual, "vertex_colors", None)
    if colors is None:
        return None
    array = np.asarray(colors)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] < 3:
        return None
    return np.asarray(array[:, :4], dtype=np.uint8)
