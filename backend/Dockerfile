# syntax=docker/dockerfile:1

# Python 3.12 to match requires-python in pyproject.toml.
FROM python:3.12-slim

# The OpenMP runtime, which numba's threading layer links against. The other system
# libraries the compiled wheels expect (libstdc++, zlib) come with the base image.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so a source change does not reinstall every package.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Kernels, terrain and the rest of the data live on a mounted volume, not in the image:
# hundreds of MB of static data in every layer would make it slow to move for no
# benefit, and every service shares the same files.
VOLUME ["/data"]
ENV PW_DATA_DIR=/data

# Non-root. Every service writes under /data (the SPICE metakernel, map tiles, raw feed
# bodies), so the mounted folder must be writable by uid 10001.
RUN useradd --create-home --uid 10001 polar && chown -R polar /app
USER polar

# This image runs the api. The workers and the migrations use it with another command
# (docker-compose.yml).
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
