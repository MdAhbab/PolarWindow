# syntax=docker/dockerfile:1

# Python 3.12, not 3.13+: numba does not yet support the newer ABI and the
# ray-march's inner loop is the one place a JIT earns its keep.
FROM python:3.12-slim AS base

# GDAL/PROJ runtime for rasterio and pyproj, and curl for the health check.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libexpat1 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so a source change does not re-resolve 109 packages.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Kernels and the DEM live on a mounted volume, not in the image: 250 MB of
# static data in every layer would make the image slow to move for no benefit,
# and the same files are shared by the api and the worker.
VOLUME ["/data"]
ENV PW_DATA_DIR=/data

# Non-root. The data volume is read-only to the API in practice; the worker is
# the only writer.
RUN useradd --create-home --uid 10001 polar && chown -R polar /app
USER polar

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
