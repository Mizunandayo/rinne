from __future__ import annotations

import sys

import numpy as np
import pytest
from PIL import Image

from rinne_reconstruction.config import Settings
from rinne_reconstruction.pipeline.base import PipelineName
from rinne_reconstruction.pipeline.instantmesh import (
    _as_rgb,
    _install_nvdiffrast_stub,
    _seed_from,
)


def test_instantmesh_is_a_pipeline_the_contract_admits() -> None:
    """The result records which reconstructor ran, so a document stays readable
    after the deployment changed. A name the schema rejects is unshippable."""
    assert "instantmesh" in PipelineName.__args__  # type: ignore[attr-defined]
    assert Settings(pipeline_name="instantmesh").pipeline_name == "instantmesh"


def test_an_unknown_pipeline_is_still_refused() -> None:
    with pytest.raises(ValueError, match="pipeline_name"):
        Settings(pipeline_name="trellis")


def test_the_nvdiffrast_stub_satisfies_the_import_and_nothing_more() -> None:
    """InstantMesh's lrm.py imports nvdiffrast at module scope but only REACHES it
    under use_texture_map=True. Stubbing it is what removes the CUDA build; the
    stub must therefore raise rather than quietly return a mock."""
    for name in ("nvdiffrast", "nvdiffrast.torch"):
        sys.modules.pop(name, None)
    try:
        _install_nvdiffrast_stub()
        import nvdiffrast.torch as dr

        assert getattr(dr, "__rinne_stub__", False) is True
        with pytest.raises(RuntimeError, match="use_texture_map=False"):
            _ = dr.RasterizeCudaContext
    finally:
        for name in ("nvdiffrast", "nvdiffrast.torch"):
            sys.modules.pop(name, None)


def test_the_seed_is_a_property_of_the_bytes() -> None:
    a = Image.new("RGB", (8, 8), (10, 20, 30))
    b = Image.new("RGB", (8, 8), (10, 20, 30))
    c = Image.new("RGB", (8, 8), (10, 20, 31))
    assert _seed_from(a) == _seed_from(b)
    assert _seed_from(a) != _seed_from(c)
    assert 0 <= _seed_from(a) <= 0xFFFFFFFF


def test_float_vertex_colours_become_rgb_bytes() -> None:
    """extract_mesh returns colours in whichever form the checkpoint produces.
    normalise() hands them to trimesh, which wants uint8 RGB."""
    out = _as_rgb(np.array([[0.0, 0.5, 1.0, 1.0], [1.0, 0.0, 0.0, 1.0]], dtype=np.float32))
    assert out is not None
    assert out.dtype == np.uint8
    assert out.shape == (2, 3)
    assert out[0].tolist() == [0, 127, 255]


def test_uint8_colours_pass_through_without_rescaling() -> None:
    out = _as_rgb(np.array([[7, 8, 9]], dtype=np.uint8))
    assert out is not None
    assert out.tolist() == [[7, 8, 9]]


@pytest.mark.parametrize("value", [None, np.zeros((0, 3), dtype=np.uint8)])
def test_absent_colours_are_none_not_an_empty_array(value: object) -> None:
    assert _as_rgb(value) is None


def test_instantmesh_frames_on_white_and_triposr_on_grey() -> None:
    """The checkpoint ships a Zero123++ UNet trained for white backgrounds. Grey is
    carried into all six generated views and reconstructed as geometry - it showed
    up as walls either side of the subject."""
    from rinne_reconstruction.imaging.segmentation import crop_and_composite
    from rinne_reconstruction.pipeline.instantmesh import _WHITE

    image = Image.new("RGB", (16, 16), (200, 30, 30))
    mask = np.zeros((16, 16), dtype=np.float32)
    mask[4:12, 4:12] = 1.0

    # 0.5 so the subject occupies half the canvas and the corner is real padding.
    grey = crop_and_composite(image, mask, foreground_ratio=0.5)
    white = crop_and_composite(image, mask, foreground_ratio=0.5, background=_WHITE)

    assert _WHITE == 1.0
    # 0.5 * 255 truncates to 127, which is the mid grey TripoSR was trained on.
    assert np.asarray(grey)[0, 0].tolist() == [127, 127, 127]
    assert np.asarray(white)[0, 0].tolist() == [255, 255, 255]
