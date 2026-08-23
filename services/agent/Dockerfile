# syntax=docker/dockerfile:1.7
#   docker build -f services/agent/Dockerfile -t rinne-agent:local .

FROM python:3.12.14-slim-bookworm AS build
# uv arrives as a PINNED BINARY rather than via the combined uv+python image.
# Two reasons, both learned the hard way:
#   1. uv.lock is written at revision 3 by uv 0.10.x. Older uv releases cannot
#      read that revision, and the old 0.5.14 pin here would have failed the
#      build with an unhelpful lockfile error.
#   2. Copying the binary lets the build and runtime stages share ONE python
#      image, which guarantees the virtualenv's interpreter symlink resolves.
#      Mismatched python images produce a venv whose `python` dangles.
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies before source: this layer caches until pyproject or the lock
# changes, which is most of the build time.
COPY services/agent/pyproject.toml services/agent/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY services/agent/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --frozen: install exactly what uv.lock says, or fail. Never resolve at
# build time — a resolver that can move is a supply chain that can move.
FROM python:3.12.14-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PORT=8080
RUN groupadd -g 10001 rinne \
 && useradd -u 10001 -g rinne -M -s /usr/sbin/nologin rinne
WORKDIR /app
COPY --from=build --chown=10001:10001 /app /app
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "rinne_agent"]
