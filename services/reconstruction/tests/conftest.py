from __future__ import annotations

import json
from collections.abc import Iterator
from io import BytesIO
from typing import Any, Protocol

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from rinne_reconstruction.app import create_app
from rinne_reconstruction.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        service_version="test-1",
        gcp_project_id="rinnehackathon",
        gcp_region="asia-southeast1",
        k_revision="rinne-reconstruction-00001-abc",
        enable_docs=False,
        # The in-process store still reports the real gs:// URI, so the SSRF
        # pattern on mesh.uri is exercised by every test that touches it.
        storage_mode="memory",
        # 48 keeps the whole suite fast while still producing a mesh with
        # thousands of faces, which is what the confidence floor and the
        # watertightness check need in order to mean anything.
        stub_resolution=48,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


class ImageFactory(Protocol):
    def __call__(
        self,
        *,
        fmt: str = ...,
        size: tuple[int, int] = ...,
        color: tuple[int, int, int] = ...,
    ) -> bytes: ...


@pytest.fixture
def image_bytes() -> ImageFactory:
    """Builds a real encoded image, rather than committing a binary fixture.

    Generating it keeps binary assets out of the repository and lets a test
    choose the colour it needs - the material heuristic reads colour, so "a
    brown image" is part of the assertion rather than an accident of whichever
    photograph somebody committed.
    """

    def _make(
        *,
        fmt: str = "JPEG",
        size: tuple[int, int] = (320, 240),
        color: tuple[int, int, int] = (150, 105, 60),
    ) -> bytes:
        buffer = BytesIO()
        Image.new("RGB", size, color).save(buffer, format=fmt)
        return buffer.getvalue()

    return _make


class MultipartFactory(Protocol):
    def __call__(
        self,
        *,
        request_document: dict[str, object] | str | None,
        images: list[tuple[bytes, str]],
        image_part_name: str = ...,
    ) -> dict[str, Any]: ...


@pytest.fixture
def multipart() -> MultipartFactory:
    """Keyword arguments for a multipart POST.

    `request` is a plain TEXT field, not a file part. That is the shape the web
    service sends (FormData.append with a JSON string) and the service accepts
    nothing else, so the two cannot drift.
    """

    def _build(
        *,
        request_document: dict[str, object] | str | None,
        images: list[tuple[bytes, str]],
        image_part_name: str = "images",
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "files": [
                (image_part_name, (f"image-{index}", data, content_type))
                for index, (data, content_type) in enumerate(images)
            ]
        }
        if request_document is not None:
            body = (
                request_document
                if isinstance(request_document, str)
                else json.dumps(request_document)
            )
            kwargs["data"] = {"request": body}
        return kwargs

    return _build
