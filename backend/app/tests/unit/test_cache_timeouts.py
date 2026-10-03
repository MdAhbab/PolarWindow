"""Verify that a stalled Redis server cannot hang a request indefinitely (H1.4)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time

import pytest

from app.config import get_settings
from app.services import cache


@pytest.mark.asyncio
async def test_stalled_redis_returns_none_within_timeout() -> None:
    active_writers: list[asyncio.StreamWriter] = []

    async def stalled_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        active_writers.append(writer)
        with contextlib.suppress(Exception):
            while True:
                data = await reader.read(1024)
                if not data:
                    break

    server = await asyncio.start_server(stalled_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    old_url = os.environ.get("PW_REDIS_URL")
    os.environ["PW_REDIS_URL"] = f"redis://127.0.0.1:{port}/0"
    get_settings.cache_clear()

    # Reset cache client before probe
    await cache.reset()
    cache._client = None
    cache._unavailable = False

    try:
        t0 = time.perf_counter()
        result = await asyncio.wait_for(cache.get("pw:x"), timeout=3.0)
        elapsed = time.perf_counter() - t0

        assert result is None
        assert elapsed < 3.0
    finally:
        server.close()
        for w in active_writers:
            w.close()
        await server.wait_closed()

        if old_url is not None:
            os.environ["PW_REDIS_URL"] = old_url
        else:
            os.environ.pop("PW_REDIS_URL", None)
        get_settings.cache_clear()

        await cache.reset()
        cache._client = None
        cache._unavailable = False
