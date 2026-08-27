from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from rinne_reconstruction.pipeline.base import (
    Device,
    ForegroundMeasurements,
    PipelineName,
    RawReconstruction,
    Reconstructor,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "schemas"
    / "reconstruction-result.schema.json"
)

JPEG = "image/jpeg"
DOCUMENT: dict[str, object] = {"schemaVersion": 1, "requestId": "scan-000001"}


def _post(client: TestClient, **kwargs: object) -> httpx2.Response:
    return client.post("/v1/reconstruct", **kwargs)  # type: ignore[arg-type]


def test_a_photograph_produces_a_contract_valid_result(
    client: TestClient, image_bytes, multipart
) -> None:
    response = _post(client, **multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)]))
    assert response.status_code == 200, response.text

    body = response.json()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert set(body).issubset(set(schema["properties"]))
    for key in schema["required"]:
        assert key in body

    assert body["requestId"] == "scan-000001"
    assert body["mesh"]["uri"] == "gs://rinne-artifacts-rinnehackathon/meshes/scan-000001.glb"
    assert body["mesh"]["format"] == "glb"
    assert body["mesh"]["upAxis"] == "y"
    assert body["mesh"]["scaleBasis"] == "assumed"
    assert len(body["mesh"]["sha256"]) == 64


def test_the_pipeline_says_it_is_a_stub(client: TestClient, image_bytes, multipart) -> None:
    """The single most important assertion in this file.

    Day 2 ships placeholder geometry by decision. pipeline.name is the field
    that exists so the payload can admit it, and the notices carry the same
    statement in a sentence a human reads.
    """
    body = _post(
        client, **multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)])
    ).json()

    assert body["pipeline"]["name"] == "stub"
    assert body["pipeline"]["device"] == "cpu"
    codes = {notice["code"] for notice in body["notices"]}
    assert "stub-pipeline" in codes
    assert "scale-assumed" in codes
    assert "confidence-uncalibrated" in codes
    assert "foreground-quality-unavailable" in codes


def test_the_mesh_is_real_even_though_the_shape_is_not(
    client: TestClient, image_bytes, multipart
) -> None:
    body = _post(
        client, **multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)])
    ).json()
    mesh = body["mesh"]

    assert mesh["faceCount"] > 100
    assert mesh["vertexCount"] > 50
    assert mesh["byteLength"] > 1000
    assert mesh["volumeCubicMeters"] > 0.0
    # Normalisation scales the longest bounding-box edge to the assumed
    # dimension. Anything else means the mesh is not in metres.
    assert max(mesh["extent"].values()) == pytest.approx(0.30, abs=1e-6)


def test_the_confidence_is_measured_and_recomputable(
    client: TestClient, image_bytes, multipart
) -> None:
    body = _post(
        client, **multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)])
    ).json()
    block = body["confidence"]

    assert block["calibrated"] is False
    assert set(block["components"]) == {
        "fieldDecisiveness",
        "watertightness",
        "volumePlausibility",
    }
    assert set(block["weights"]) == set(block["components"])
    assert round(sum(block["weights"].values()), 4) == 1.0

    recomputed = sum(
        block["weights"][name] * block["components"][name] for name in block["weights"]
    )
    assert round(recomputed, 4) == block["score"]
    assert 0.0 <= block["score"] <= 1.0


def test_the_material_guess_comes_from_the_photograph(
    client: TestClient, image_bytes, multipart
) -> None:
    # A mid-brown image lands in the cardboard rule: hue ~30, saturation ~0.6,
    # value ~0.59. The mesh is coloured by projecting the photograph onto it,
    # so this is the real signal path and not a fixed answer.
    body = _post(
        client,
        **multipart(request_document=DOCUMENT, images=[(image_bytes(color=(150, 105, 60)), JPEG)]),
    ).json()

    assert body["material"]["name"] == "cardboard"
    assert body["material"]["basis"] == "heuristic-v1"
    assert body["material"]["densityKilogramsPerCubicMeter"] == 150
    assert body["material"]["massKilograms"] > 0


def test_the_same_photograph_produces_the_same_mesh(
    client: TestClient, image_bytes, multipart
) -> None:
    image = image_bytes()
    first = _post(client, **multipart(request_document=DOCUMENT, images=[(image, JPEG)])).json()
    second = _post(
        client,
        **multipart(
            request_document={**DOCUMENT, "requestId": "scan-000002"}, images=[(image, JPEG)]
        ),
    ).json()

    assert first["pipeline"]["seed"] == second["pipeline"]["seed"]
    assert first["mesh"]["sha256"] == second["mesh"]["sha256"]
    assert first["confidence"]["score"] == second["confidence"]["score"]


def test_extra_images_are_accepted_and_the_narrowing_is_declared(
    client: TestClient, image_bytes, multipart
) -> None:
    body = _post(
        client,
        **multipart(
            request_document=DOCUMENT,
            images=[(image_bytes(), JPEG), (image_bytes(size=(200, 200)), JPEG)],
        ),
    ).json()

    assert body["images"] == {
        "received": 2,
        "accepted": 2,
        "used": 1,
        "reencoded": True,
        "longestEdgePixels": 320,
    }
    assert "images-ignored" in {notice["code"] for notice in body["notices"]}


def test_a_second_request_with_the_same_id_is_refused_rather_than_overwriting(
    client: TestClient, image_bytes, multipart
) -> None:
    """ifGenerationMatch=0 semantics, exercised through the in-memory store.

    Overwriting would silently replace an artifact a Firestore record already
    points at, which is a wrong answer rather than an error.
    """
    args = multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)])
    assert _post(client, **args).status_code == 200

    response = _post(client, **multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)]))
    assert response.status_code == 409
    assert response.json()["error"] == "mesh already exists for this requestId"


def test_a_missing_request_part_is_refused(client: TestClient, image_bytes, multipart) -> None:
    response = _post(client, **multipart(request_document=None, images=[(image_bytes(), JPEG)]))
    assert response.status_code == 400
    assert response.json()["error"] == "request part is missing or is not text"


def test_a_request_part_that_is_not_json_is_refused(
    client: TestClient, image_bytes, multipart
) -> None:
    response = _post(client, **multipart(request_document="{nope", images=[(image_bytes(), JPEG)]))
    assert response.status_code == 400
    assert response.json()["error"] == "request part is not valid JSON"


def test_a_request_id_that_could_escape_the_prefix_is_refused(
    client: TestClient, image_bytes, multipart
) -> None:
    response = _post(
        client,
        **multipart(
            request_document={"schemaVersion": 1, "requestId": "../../../etc/passwd"},
            images=[(image_bytes(), JPEG)],
        ),
    )
    assert response.status_code == 400
    assert response.json()["error"] == "request part failed contract validation"


def test_images_under_the_wrong_part_name_are_not_images(
    client: TestClient, image_bytes, multipart
) -> None:
    """The part name is part of the contract, not a convention.

    An image posted as `photo` is not an image as far as this endpoint is
    concerned, and saying so is more useful than reconstructing nothing.
    """
    response = _post(
        client,
        **multipart(
            request_document=DOCUMENT,
            images=[(image_bytes(), JPEG)],
            image_part_name="photo",
        ),
    )
    assert response.status_code == 400
    assert response.json()["error"] == "at least one image part is required"


def test_more_than_four_images_is_refused(client: TestClient, image_bytes, multipart) -> None:
    response = _post(
        client,
        **multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)] * 5),
    )
    assert response.status_code == 400
    assert response.json()["error"] == "too many image parts"


def test_a_disallowed_image_type_is_refused_with_the_rule_not_the_filename(
    client: TestClient, image_bytes, multipart
) -> None:
    response = _post(
        client,
        **multipart(
            request_document=DOCUMENT,
            images=[(image_bytes(fmt="GIF"), "image/gif")],
        ),
    )
    assert response.status_code == 415
    body = response.json()
    assert body["error"] == "image type is not one of jpeg, png, webp"
    # The rule, and nothing else. No filename, no byte offset, no PIL message.
    assert set(body) == {"error", "requestId"}
    assert "image-0" not in response.text


def test_oversized_metadata_is_refused(client: TestClient, image_bytes, multipart) -> None:
    response = _post(
        client,
        **multipart(
            request_document={**DOCUMENT, "metadata": {"note": "x" * 5000}},
            images=[(image_bytes(), JPEG)],
        ),
    )
    assert response.status_code == 400
    assert response.json()["error"] == "request metadata exceeds the size limit"


def test_a_json_body_is_refused_with_the_reason_it_actually_failed(client: TestClient) -> None:
    """Starlette returns an EMPTY form for a JSON body rather than raising.

    Without an explicit content-type check the caller is told its `request`
    part is missing, which is true and useless. This asserts it gets told the
    endpoint is multipart-only instead.
    """
    response = client.post("/v1/reconstruct", json={"schemaVersion": 1, "requestId": "scan-000001"})
    assert response.status_code == 415
    assert response.json()["error"] == "request must be multipart/form-data"


def test_the_assumed_dimension_from_the_request_is_honoured(
    client: TestClient, image_bytes, multipart
) -> None:
    body = _post(
        client,
        **multipart(
            request_document={**DOCUMENT, "assumedLongestDimensionMeters": 1.25},
            images=[(image_bytes(), JPEG)],
        ),
    ).json()
    assert max(body["mesh"]["extent"].values()) == pytest.approx(1.25, abs=1e-6)


def test_timings_are_reported_for_every_stage(client: TestClient, image_bytes, multipart) -> None:
    timings = _post(
        client, **multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)])
    ).json()["timings"]

    assert set(timings) == {"validationMs", "inferenceMs", "meshMs", "uploadMs", "totalMs"}
    assert all(value >= 0 for value in timings.values())
    assert timings["totalMs"] >= timings["inferenceMs"]


class _SegmentingStub:
    """The stub, plus the two numbers a segmentation mask would have measured.

    Stands in for TripoSR so the four-component path is covered by a test that
    needs neither torch, nor a GPU, nor 1.7GB of weights.
    """

    def __init__(self, inner: Reconstructor, *, coverage: float, border_fraction: float) -> None:
        self._inner = inner
        self._foreground = ForegroundMeasurements(
            coverage=coverage, border_fraction=border_fraction
        )

    @property
    def name(self) -> PipelineName:
        return self._inner.name

    @property
    def version(self) -> str:
        return self._inner.version

    @property
    def device(self) -> Device:
        return self._inner.device

    def reconstruct(self, image: Image.Image) -> RawReconstruction:
        return replace(self._inner.reconstruct(image), foreground=self._foreground)


def test_a_segmenting_pipeline_reports_four_components_and_the_full_weights(
    app: Any, image_bytes, multipart
) -> None:
    """The Day 3 restoration, asserted end to end through the route.

    0.45 / 0.30 / 0.15 / 0.10 with no schemaVersion bump, because the weights
    ship inside the payload - which is the entire reason they are there.
    """
    with TestClient(app) as client:
        app.state.pipeline = _SegmentingStub(app.state.pipeline, coverage=0.35, border_fraction=0.0)
        body = _post(
            client, **multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)])
        ).json()

    block = body["confidence"]
    assert set(block["components"]) == {
        "fieldDecisiveness",
        "watertightness",
        "volumePlausibility",
        "foregroundQuality",
    }
    assert block["weights"] == {
        "fieldDecisiveness": 0.45,
        "watertightness": 0.30,
        "volumePlausibility": 0.10,
        "foregroundQuality": 0.15,
    }
    assert block["components"]["foregroundQuality"] == 1.0

    recomputed = sum(
        block["weights"][name] * block["components"][name] for name in block["weights"]
    )
    assert round(recomputed, 4) == block["score"]
    assert "foreground-quality-unavailable" not in {n["code"] for n in body["notices"]}


def test_a_badly_framed_photograph_pushes_the_score_down(app: Any, image_bytes, multipart) -> None:
    """A subject running off the frame edge is evidence, and it costs score."""
    with TestClient(app) as client:
        app.state.pipeline = _SegmentingStub(app.state.pipeline, coverage=0.95, border_fraction=0.8)
        body = _post(
            client, **multipart(request_document=DOCUMENT, images=[(image_bytes(), JPEG)])
        ).json()

    assert body["confidence"]["components"]["foregroundQuality"] == 0.0
