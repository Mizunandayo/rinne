# syntax=docker/dockerfile:1.7
# docker build -f services/reconstruction/Dockerfile -t rinne-reconstruction:local .
# Five stages: two vendored sources, verified weights, python deps, runtime.
# ~8GB with triposr alone; ~16GB once InstantMesh's two stages are included.





# 1. TripoSR source, at a pinned commit
FROM python:3.12.14-slim-bookworm AS source
ARG TRIPOSR_SHA=107cefdc244c39106fa830359024f6a2f1c78871
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /clone
# Cone-mode sparse checkout keeps ~60MB of example images and figures out of the fetch
RUN git clone -q --filter=blob:none --no-checkout \
      https://github.com/VAST-AI-Research/TripoSR.git . \
 && git sparse-checkout set tsr \
 && git checkout -q "${TRIPOSR_SHA}" \
 && test "$(git rev-parse HEAD)" = "${TRIPOSR_SHA}" \
 && mkdir -p /opt/triposr/src \
 && cp -r tsr /opt/triposr/src/tsr \
 && cp LICENSE /opt/triposr/src/TRIPOSR-LICENSE

# 1b. InstantMesh source, at a pinned commit. src/ and configs/ only: the repo
# also carries examples, assets and the training rig, none of which run here.
FROM python:3.12.14-slim-bookworm AS instantmesh-source
ARG INSTANTMESH_SHA=08822c52fdc399b93ea00e4fa9e596344ed52ccc
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /clone
RUN git clone -q --filter=blob:none --no-checkout \
      https://github.com/TencentARC/InstantMesh.git . \
 && git sparse-checkout set src configs LICENSE \
 && git checkout -q "${INSTANTMESH_SHA}" \
 && test "$(git rev-parse HEAD)" = "${INSTANTMESH_SHA}" \
 && mkdir -p /opt/instantmesh/src \
 && cp -r src configs /opt/instantmesh/src/ \
 && cp LICENSE /opt/instantmesh/src/INSTANTMESH-LICENSE \
 && test -f /opt/instantmesh/src/configs/instant-nerf-large.yaml

# 2. Weights, every one of them sha256-verified
FROM python:3.12.14-slim-bookworm AS weights
ARG TRIPOSR_HF_REVISION=5b521936b01fbe1890f6f9baed0254ab6351c04a
ARG TRIPOSR_CONFIG_SHA256=74ca708ce086bf68e97709ea6b3d91f14717921c04691e84043f0eb8fcc68e62
ARG TRIPOSR_CKPT_SHA256=429e2c6b22a0923967459de24d67f05962b235f79cde6b032aa7ed2ffcd970ee
ARG DINO_REVISION=f205d5d8e640a89a2b8ef0369670dfc37cc07fc2
ARG DINO_CONFIG_SHA256=b87c0270b97db085fd82cf114a761fd0f62ae7914fbd407c752a2260646b689c
ARG U2NETP_URL=https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx
ARG U2NETP_SHA256=309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8
ARG HUGGINGFACE_HUB_VERSION=0.36.2
ENV HF_HOME=/opt/huggingface
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/triposr/weights
# TSR.from_pretrained takes a DIRECTORY as well as a hub id.
RUN curl -fsSL -o config.yaml \
      "https://huggingface.co/stabilityai/TripoSR/resolve/${TRIPOSR_HF_REVISION}/config.yaml" \
 && curl -fsSL -o model.ckpt \
      "https://huggingface.co/stabilityai/TripoSR/resolve/${TRIPOSR_HF_REVISION}/model.ckpt" \
 && echo "${TRIPOSR_CONFIG_SHA256}  config.yaml" | sha256sum -c - \
 && echo "${TRIPOSR_CKPT_SHA256}  model.ckpt" | sha256sum -c -

RUN mkdir -p /opt/u2netp \
 && curl -fsSL -o /opt/u2netp/u2netp.onnx "${U2NETP_URL}" \
 && echo "${U2NETP_SHA256}  /opt/u2netp/u2netp.onnx" | sha256sum -c -


# InstantMesh's two stages. Pinned by HF revision rather than per-file sha256:
# a revision IS the content hash of the whole tree, and the Zero123++ snapshot is
# 17 files. The custom pipeline lives in a SEPARATE repo from the weights, and is
# vendored as pipeline.py so nothing is fetched from the network at load time.
ARG INSTANTMESH_HF_REVISION=b785b4ecfb6636ef34a08c748f96f6a5686244d0
ARG ZERO123PLUS_REVISION=2da07e89919e1a130c9b5add1584c70c7aa065fd
ARG ZERO123PLUS_PIPELINE_REVISION=983e66d28a3637ddd8e3e2fd8165cdff32230872

RUN pip install --no-cache-dir "huggingface-hub==${HUGGINGFACE_HUB_VERSION}" \
 && python -c "\
from huggingface_hub import hf_hub_download, snapshot_download; \
import shutil, os; \
os.makedirs('/opt/instantmesh/weights', exist_ok=True); \
[shutil.copy(hf_hub_download(repo_id='TencentARC/InstantMesh', filename=f, revision='${INSTANTMESH_HF_REVISION}'), f'/opt/instantmesh/weights/{f}') for f in ('instant_nerf_large.ckpt', 'diffusion_pytorch_model.bin')]; \
snapshot_download(repo_id='sudo-ai/zero123plus-v1.2', revision='${ZERO123PLUS_REVISION}', local_dir='/opt/zero123plus'); \
shutil.copy(hf_hub_download(repo_id='sudo-ai/zero123plus-pipeline', filename='pipeline.py', revision='${ZERO123PLUS_PIPELINE_REVISION}'), '/opt/zero123plus/pipeline.py')" \
 && test -f /opt/instantmesh/weights/instant_nerf_large.ckpt \
 && test -f /opt/zero123plus/pipeline.py \
 && test -f /opt/zero123plus/model_index.json

RUN pip install --no-cache-dir "huggingface-hub==${HUGGINGFACE_HUB_VERSION}" \
 && python -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='facebook/dino-vitb16', filename='config.json', revision='${DINO_REVISION}')" \
 && SNAPSHOT="${HF_HOME}/hub/models--facebook--dino-vitb16/snapshots/${DINO_REVISION}" \
 && echo "${DINO_CONFIG_SHA256}  ${SNAPSHOT}/config.json" | sha256sum -c - \
 && cp --remove-destination "$(readlink -f "${SNAPSHOT}/config.json")" "${SNAPSHOT}/config.json" \
 && mkdir -p "${HF_HOME}/hub/models--facebook--dino-vitb16/refs" \
 && printf '%s' "${DINO_REVISION}" > "${HF_HOME}/hub/models--facebook--dino-vitb16/refs/main"

# TripoSR builds its ViT from the config alone and takes the weights from its own
# checkpoint. InstantMesh's encoder calls ViTModel.from_pretrained, which wants the
# real thing - baked here so startup never depends on the network. tf_model.h5 is
# the TensorFlow copy of the same weights and is excluded.
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download(repo_id='facebook/dino-vitb16', revision='${DINO_REVISION}', allow_patterns=['config.json', 'preprocessor_config.json', 'pytorch_model.bin'])" \
 && test -f "${HF_HOME}/hub/models--facebook--dino-vitb16/snapshots/${DINO_REVISION}/pytorch_model.bin"

# 3. Python dependencies
FROM python:3.12.14-slim-bookworm AS build
# Pinned uv binary, not the uv+python image: uv.lock is revision 3, and one shared
# python image keeps the venv's interpreter symlink valid.
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# --group gpu: torch and what the vendored tsr tree imports. This is the layer
# that makes the image ~8GB, so it caches on pyproject.toml and uv.lock alone.
COPY services/reconstruction/pyproject.toml services/reconstruction/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group gpu --no-install-project

COPY services/reconstruction/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group gpu

FROM python:3.12.14-slim-bookworm AS runtime
# numpy/scipy/skimage wheels link the system libgomp instead of vendoring it.
# Without this the container starts, then dies on the first `import skimage`.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*


ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PORT=8080 \
    HF_HUB_OFFLINE=1 \
    HF_HOME=/opt/huggingface \
    PIPELINE_NAME=triposr

RUN groupadd -g 10001 rinne \
 && useradd -u 10001 -g rinne -M -s /usr/sbin/nologin rinne
WORKDIR /app
COPY --from=build --chown=10001:10001 /app /app
COPY --from=source --chown=10001:10001 /opt/triposr/src /opt/triposr/src
COPY --from=weights --chown=10001:10001 /opt/triposr/weights /opt/triposr/weights
COPY --from=weights --chown=10001:10001 /opt/u2netp /opt/u2netp
COPY --from=weights --chown=10001:10001 /opt/huggingface /opt/huggingface
COPY --from=instantmesh-source --chown=10001:10001 /opt/instantmesh/src /opt/instantmesh/src
COPY --from=weights --chown=10001:10001 /opt/instantmesh/weights /opt/instantmesh/weights
COPY --from=weights --chown=10001:10001 /opt/zero123plus /opt/zero123plus
USER 10001:10001
EXPOSE 8080

# No HEALTHCHECK: Cloud Run ignores it and uses the probe flags from deploy-all.ps1.
CMD ["python", "-m", "rinne_reconstruction"]
