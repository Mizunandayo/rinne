# syntax=docker/dockerfile:1.7
#   docker build -f services/agent/Dockerfile -t rinne-agent:local .

FROM ghcr.io/astral-sh/uv:0.5.14-python3.12-bookworm-slim AS build
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
FROM python:3.12.8-slim-bookworm AS runtime
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
