"""InstantMesh: Zero123++ invents six consistent views, an LRM reconstructs from them.

Two things make this fit the existing service without touching anything downstream.
`extract_mesh(use_texture_map=False)` returns the same (vertices, faces, colours)
triple TripoSR does, so `normalise()` and `measure()` are unchanged. And nvdiffrast
is imported by `src/models/lrm.py` but only REACHED under `use_texture_map=True`,
so it is stubbed rather than built - which is what makes this deployable at all.
"""

from __future__ import annotations

import logging
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from PIL import Image

from rinne_reconstruction.imaging.segmentation import U2netpSegmenter, crop_and_composite
from rinne_reconstruction.mesh.texture import BakedTexture, TextureBakeError, bake
from rinne_reconstruction.pipeline.base import Device, PipelineName, RawReconstruction

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

_ZERO123PLUS_STEPS: Final = 75
_MESH_THRESHOLD: Final = 10.0
# Upstream resizes the six views bicubic. Matching it keeps this a faithful port.
_BICUBIC: Final = 3
# The InstantMesh checkpoint ships "a customized Zero123++ UNet for
# white-background generation". TripoSR's mid grey would be reconstructed as
# geometry, which is exactly what it did: walls either side of the subject.
_WHITE: Final = 1.0
# Coarse grid over the triplane's own [-1, 1] space, which is where
# extract_mesh cuts. 48^3 is 110k queries: negligible on an L4, and enough
# to say whether the field committed or hovered at the threshold.
_FIELD_SAMPLES: Final = 48
#: An atlas is a million points; one call would not fit in VRAM.
_SAMPLE_CHUNK: Final = 262_144
#: A noun phrase. Zero123++ never saw a sentence during fine-tuning.
_PROMPT_LIMIT: Final = 64
#: Zero123++'s rig: azimuths 30/90/150/210/270/330 at alternating +20 and
#: -10 elevation. Photographs must arrive in that order to stand in for it.
_RIG_VIEWS: Final = 6


class _RefusedAttribute:
    """A stub that fails loudly. Reaching nvdiffrast means the texture path ran,
    which this service never asks for; a silent no-op would ship a wrong mesh."""

    def __init__(self, module: str) -> None:
        self._module = module

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(
            f"{self._module}.{name} was called. This build stubs nvdiffrast because "
            "the UV/texture path is never used; extract_mesh must run with "
            "use_texture_map=False."
        )


class InstantMeshReconstructor:
    """Holds the diffusion pipeline and the LRM. Both stay resident on the L4."""

    def __init__(
        self,
        *,
        diffusion: Any,
        model: Any,
        segmenter: U2netpSegmenter,
        device: Device,
        commit_sha: str,
        marching_cubes_resolution: int,
        foreground_ratio: float,
        diffusion_steps: int,
        texture_resolution: int,
        texture_faces: int,
        prompt_from_label: bool,
        multiview: bool,
    ) -> None:
        self._diffusion = diffusion
        self._model = model
        self._segmenter = segmenter
        self._device: Device = device
        self._commit_sha = commit_sha
        self._resolution = marching_cubes_resolution
        self._foreground_ratio = foreground_ratio
        self._diffusion_steps = diffusion_steps
        self._texture_resolution = texture_resolution
        self._texture_faces = texture_faces
        self._prompt_from_label = prompt_from_label
        self._multiview = multiview

    @property
    def name(self) -> PipelineName:
        return "instantmesh"

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
        import torch
        from einops import rearrange
        from src.utils.camera_util import get_zero123plus_input_cameras
        from torchvision.transforms import v2

        foreground = self._segmenter.segment(image)
        framed = crop_and_composite(
            image,
            foreground.mask,
            foreground_ratio=self._foreground_ratio,
            background=_WHITE,
        )

        seed = _seed_from(framed)
        torch.manual_seed(seed)
        generator = torch.Generator(device=self._device).manual_seed(seed)

        # OBSERVED beats INVENTED. Stage 2 is a sparse-view reconstructor that
        # consumes six images at a fixed rig; stage 1 exists only to hallucinate
        # those six when nobody photographed them. Given the real thing, skip it.
        photographed = self._real_views(views)
        if photographed is not None:
            return self._from_views(photographed, foreground, seed)

        # Zero123++ inherits Stable Diffusion's text pathway: `prompt` is encoded
        # and combined with the visual embedding. It was FINE-TUNED with an empty
        # prompt, so a label is off-distribution - it may sharpen the six views or
        # cost their consistency, which is what the reconstructor depends on. Off
        # by one env var, and the result records whether it was used.
        prompt = label.strip()[:_PROMPT_LIMIT] if (self._prompt_from_label and label) else ""
        sheet = self._diffusion(
            framed,
            prompt=prompt,
            num_inference_steps=self._diffusion_steps,
            generator=generator,
        ).images[0]
        if prompt:
            logger.info("conditioned the view synthesis", extra={"prompt": prompt})

        # Zero123++ answers one 3x2 sheet of 320px tiles, not six images.
        sheet_rgb = np.asarray(sheet, dtype=np.float32) / 255.0
        tiled = torch.from_numpy(sheet_rgb).permute(2, 0, 1).contiguous()
        six = rearrange(tiled, "c (n h) (m w) -> (n m) c h w", n=3, m=2)
        six = v2.functional.resize(six, 320, interpolation=_BICUBIC, antialias=True).clamp(0, 1)

        cameras = get_zero123plus_input_cameras(batch_size=1, radius=4.0).to(self._device)
        batch = six.unsqueeze(0).to(self._device)

        with torch.no_grad():
            planes = self._model.forward_planes(batch, cameras)
            vertices, faces, vertex_colors = self._model.extract_mesh(
                planes,
                mesh_resolution=self._resolution,
                mesh_threshold=_MESH_THRESHOLD,
                use_texture_map=False,
            )

        surface = np.asarray(vertices, dtype=np.float32)
        triangles = np.asarray(faces, dtype=np.int64)
        baked = self._bake(planes, surface, triangles)

        return RawReconstruction(
            vertices=baked.vertices if baked else surface,
            faces=baked.faces if baked else triangles,
            vertex_colors=None if baked else _as_rgb(vertex_colors),
            deviation=self._field_deviation(planes),
            seed=seed,
            foreground=foreground.measurements,
            uv=baked.uv if baked else None,
            texture=baked.image if baked else None,
        )

    def _real_views(self, views: list[Image.Image] | None) -> Any:
        """The six photographs, framed and stacked, or None to synthesise."""
        import torch
        from torchvision.transforms import v2

        if not self._multiview or views is None or len(views) < _RIG_VIEWS:
            return None

        frames = []
        for view in views[:_RIG_VIEWS]:
            found = self._segmenter.segment(view)
            framed = crop_and_composite(
                view,
                found.mask,
                foreground_ratio=self._foreground_ratio,
                background=_WHITE,
            )
            rgb = np.asarray(framed.convert("RGB"), dtype=np.float32) / 255.0
            frames.append(torch.from_numpy(rgb).permute(2, 0, 1).contiguous())

        stacked = torch.stack(frames, dim=0)
        return v2.functional.resize(stacked, 320, interpolation=_BICUBIC, antialias=True).clamp(
            0, 1
        )

    def _from_views(self, six: Any, foreground: Any, seed: int) -> RawReconstruction:
        """Stage 2 alone, on photographs rather than on generated views."""
        import torch
        from src.utils.camera_util import get_zero123plus_input_cameras

        cameras = get_zero123plus_input_cameras(batch_size=1, radius=4.0).to(self._device)
        batch = six.unsqueeze(0).to(self._device)

        with torch.no_grad():
            planes = self._model.forward_planes(batch, cameras)
            vertices, faces, vertex_colors = self._model.extract_mesh(
                planes,
                mesh_resolution=self._resolution,
                mesh_threshold=_MESH_THRESHOLD,
                use_texture_map=False,
            )

        logger.info("reconstructed from photographs", extra={"views": _RIG_VIEWS})
        surface = np.asarray(vertices, dtype=np.float32)
        triangles = np.asarray(faces, dtype=np.int64)
        baked = self._bake(planes, surface, triangles)
        return RawReconstruction(
            vertices=baked.vertices if baked else surface,
            faces=baked.faces if baked else triangles,
            vertex_colors=None if baked else _as_rgb(vertex_colors),
            deviation=self._field_deviation(planes),
            seed=seed,
            foreground=foreground.measurements,
            uv=baked.uv if baked else None,
            texture=baked.image if baked else None,
        )

    def _bake(
        self, planes: Any, vertices: NDArray[np.float32], faces: NDArray[np.int64]
    ) -> BakedTexture | None:
        """An atlas beats one colour per vertex, so the geometry under it can be
        lighter. Any failure returns None and the caller keeps vertex colour: a
        missing texture is a worse mesh, not a failed request."""
        if self._texture_resolution <= 0:
            return None
        try:
            light = _reduce(vertices, faces, self._texture_faces)
            return bake(
                light[0],
                light[1],
                sample=lambda points: self._sample_rgb(planes, points),
                resolution=self._texture_resolution,
            )
        except (TextureBakeError, ValueError, RuntimeError, MemoryError):
            logger.exception("texture bake failed; falling back to vertex colour")
            return None

    def _sample_rgb(self, planes: Any, points: NDArray[np.float32]) -> NDArray[np.float32]:
        """Colour straight from the field, at texel resolution rather than at
        vertex resolution. Chunked because an atlas is a million queries."""
        import torch

        out: list[NDArray[np.float32]] = []
        with torch.no_grad():
            for start in range(0, points.shape[0], _SAMPLE_CHUNK):
                block = torch.from_numpy(points[start : start + _SAMPLE_CHUNK]).to(self._device)
                sampled = self._model.synthesizer.forward_points(planes, block.unsqueeze(0))
                rgb = sampled["rgb"] if isinstance(sampled, dict) else None
                if rgb is None:
                    raise TextureBakeError("the synthesizer returned no rgb")
                out.append(np.asarray(rgb.reshape(-1, 3).float().cpu().numpy(), dtype=np.float32))
        return np.concatenate(out, axis=0) if out else np.zeros((0, 3), dtype=np.float32)

    def _field_deviation(self, planes: Any) -> NDArray[np.float32]:
        """How far the density field sat from the threshold it was cut at."""
        import torch

        axis = torch.linspace(-1.0, 1.0, _FIELD_SAMPLES, device=self._device)
        grid = torch.stack(torch.meshgrid(axis, axis, axis, indexing="ij"), dim=-1)
        points = grid.reshape(1, -1, 3)

        with torch.no_grad():
            sampled = self._model.synthesizer.forward_points(planes, points)

        field = sampled.get("sigma") if isinstance(sampled, dict) else None
        if field is None:
            return np.zeros(0, dtype=np.float32)
        # Re-typed at the boundary: torch is Any here, and the rest of the service
        # is entitled to a real dtype rather than whatever it hands back.
        values: NDArray[np.float32] = np.asarray(
            field.reshape(-1).float().cpu().numpy(), dtype=np.float32
        )
        deviation: NDArray[np.float32] = np.abs(values - _MESH_THRESHOLD)
        return deviation


def build_instantmesh_reconstructor(
    *,
    source_dir: str,
    weights_dir: str,
    zero123plus_dir: str,
    segmentation_model_path: str,
    commit_sha: str,
    marching_cubes_resolution: int,
    foreground_ratio: float,
    diffusion_steps: int = _ZERO123PLUS_STEPS,
    texture_resolution: int = 0,
    texture_faces: int = 40_000,
    prompt_from_label: bool = False,
    multiview: bool = True,
) -> InstantMeshReconstructor:
    """Load both stages. Called from the lifespan block, before the port answers."""
    import torch
    from diffusers import DiffusionPipeline, EulerAncestralDiscreteScheduler
    from omegaconf import OmegaConf

    _install_nvdiffrast_stub()

    source = Path(source_dir)
    if not (source / "src" / "models" / "lrm.py").is_file():
        raise FileNotFoundError(f"vendored InstantMesh source not found at {source}")
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

    weights = Path(weights_dir)
    checkpoint = weights / "instant_nerf_large.ckpt"
    unet = weights / "diffusion_pytorch_model.bin"
    config = source / "configs" / "instant-nerf-large.yaml"
    for required in (checkpoint, unet, config):
        if not required.is_file():
            raise FileNotFoundError(f"InstantMesh requires {required}")

    from src.utils.train_util import instantiate_from_config

    device: Device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    # trust_remote_code is normally a network trust decision. It is not one here:
    # pipeline.py was vendored into the image at a pinned revision by the build,
    # local_files_only forbids a fetch, and the container has no path to change it.
    diffusion = DiffusionPipeline.from_pretrained(
        zero123plus_dir,
        custom_pipeline=zero123plus_dir,
        torch_dtype=dtype,
        local_files_only=True,
        trust_remote_code=True,
    )
    diffusion.scheduler = EulerAncestralDiscreteScheduler.from_config(
        diffusion.scheduler.config, timestep_spacing="trailing"
    )
    diffusion.unet.load_state_dict(
        torch.load(unet, map_location="cpu", weights_only=True), strict=True
    )
    diffusion.to(device)

    loaded = OmegaConf.load(config)
    model = instantiate_from_config(loaded.model_config)
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)["state_dict"]
    model.load_state_dict(
        {k[len("lrm_generator.") :]: v for k, v in state.items() if k.startswith("lrm_generator.")},
        strict=True,
    )
    model.eval().to(device)

    return InstantMeshReconstructor(
        diffusion=diffusion,
        model=model,
        segmenter=U2netpSegmenter(segmentation_model_path),
        device=device,
        commit_sha=commit_sha,
        marching_cubes_resolution=marching_cubes_resolution,
        foreground_ratio=foreground_ratio,
        diffusion_steps=diffusion_steps,
        texture_resolution=texture_resolution,
        texture_faces=texture_faces,
        prompt_from_label=prompt_from_label,
        multiview=multiview,
    )


def _install_nvdiffrast_stub() -> None:
    """`import nvdiffrast.torch as dr` must SUCCEED - only using dr may fail. So the
    parent carries the submodule as a real attribute and only the leaf refuses."""
    if "nvdiffrast.torch" in sys.modules:
        return

    leaf = types.ModuleType("nvdiffrast.torch")
    leaf.__doc__ = "Rinne stub. Imported by InstantMesh's lrm.py, never called."
    leaf.__rinne_stub__ = True  # type: ignore[attr-defined]
    leaf.__getattr__ = _RefusedAttribute("nvdiffrast.torch").__getattr__  # type: ignore[method-assign]

    parent = sys.modules.get("nvdiffrast") or types.ModuleType("nvdiffrast")
    parent.__doc__ = leaf.__doc__
    parent.__rinne_stub__ = True  # type: ignore[attr-defined]
    parent.torch = leaf  # type: ignore[attr-defined]

    sys.modules["nvdiffrast"] = parent
    sys.modules["nvdiffrast.torch"] = leaf


def _reduce(
    vertices: NDArray[np.float32], faces: NDArray[np.int64], target: int
) -> tuple[NDArray[np.float32], NDArray[np.int64]]:
    """Lighter geometry before unwrapping: the atlas carries the detail, and the
    bake costs time per triangle."""
    import trimesh

    if target <= 0 or faces.shape[0] <= target:
        return vertices, faces
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    reduced = mesh.simplify_quadric_decimation(face_count=target)
    return (
        np.asarray(reduced.vertices, dtype=np.float32),
        np.asarray(reduced.faces, dtype=np.int64),
    )


def _as_rgb(colors: Any) -> NDArray[np.uint8] | None:
    if colors is None:
        return None
    array = np.asarray(colors)
    if array.ndim != 2 or array.shape[0] == 0:
        return None
    if array.dtype != np.uint8:
        array = (np.clip(array, 0.0, 1.0) * 255.0).astype(np.uint8)
    return np.ascontiguousarray(array[:, :3])


def _seed_from(image: Image.Image) -> int:
    """Same rule as triposr: the seed is a property of the bytes, so a re-run of
    the same scan is reproducible without the caller having to pass one."""
    import hashlib

    digest = hashlib.sha256(image.tobytes()).digest()
    return int.from_bytes(digest[:4], "big")
