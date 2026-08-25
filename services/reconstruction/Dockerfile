# syntax=docker/dockerfile:1.7
# docker build -f services/reconstruction/Dockerfile -t rinne-reconstruction:local .
# Two stages, not four: TripoSR source + weights deferred. See Blueprint 0b.

FROM python:3.12.14-slim-bookworm AS build
# Pinned uv binary, not the uv+python image: uv.lock is revision 3, and one shared
# python image keeps the venv's interpreter symlink valid.
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Deps before source so this layer caches. No `--group gpu`: the stub is numpy and
# scikit-image only, and torch would add ~2.5GB it never imports.
COPY services/reconstruction/pyproject.toml services/reconstruction/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY services/reconstruction/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12.14-slim-bookworm AS runtime
# numpy/scipy/skimage wheels link the system libgomp instead of vendoring it.
# Without this the container starts, then dies on the first `import skimage`.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Armed before there is anything to fetch: a runtime HF download would race Cloud
# Run's 240s startup-probe ceiling once TripoSR lands.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PORT=8080 \
    HF_HUB_OFFLINE=1

RUN groupadd -g 10001 rinne \
 && useradd -u 10001 -g rinne -M -s /usr/sbin/nologin rinne
WORKDIR /app
COPY --from=build --chown=10001:10001 /app /app
USER 10001:10001
EXPOSE 8080

# No HEALTHCHECK: Cloud Run ignores it and uses the probe flags from deploy-all.ps1.
CMD ["python", "-m", "rinne_reconstruction"]
