"""Redis cache and single-flight, keyed by the quantised request.

Three mechanisms, in the order of how much they buy (system-design section 6):

1. **Quantisation** happens upstream, in ``geometry_service.validate_window``.
   It is what makes a continuous slider drag collapse onto a small set of
   repeated keys. Without it the hit rate on the product's primary interaction
   is zero and nothing below matters.
2. **The cache itself**, orjson + zstd. A 2,835-sample timeline is ~230 KB of
   JSON and ~35 KB compressed, so the network round trip to Redis costs less
   than re-deriving it.
3. **Single-flight.** When the slider lands on a fresh key, seven sites fetch
   at once and would otherwise each compute the same thing. A short Redis lock
   means one computes and the rest wait on the result.

Every operation degrades to a no-op if Redis is unreachable. The four numbers
must not depend on a cache being up, so a Redis outage costs latency and
nothing else -- reported honestly as ``meta.cache = "bypass"``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import orjson
import zstandard as zstd

from app.config import ENGINE_VERSION, get_settings

log = logging.getLogger(__name__)

_compressor = zstd.ZstdCompressor(level=3)
_decompressor = zstd.ZstdDecompressor()

_client: Any = None
_unavailable = False

#: Version of the cached *payload shape*, independent of the physics.
#:
#: ``ENGINE_VERSION`` covers a change to the numbers. It does not cover a
#: change to the response contract -- a field added to an arc, say -- and a
#: cached body of the old shape then fails response validation and turns a
#: cache hit into a 500. Bump this whenever a cached payload's shape changes.
PAYLOAD_SCHEMA = "5"


async def get_client() -> Any:
    """Lazily connect. One failure disables Redis for the process lifetime.

    Retrying a dead Redis on every request would add its connect timeout to
    every single response -- turning a degradation into an outage. The flag is
    reset only by a restart, which is the right granularity for a demo.
    """
    global _client, _unavailable
    s = get_settings()
    if not s.redis_enabled or _unavailable:
        return None
    if _client is None:
        try:
            import redis.asyncio as aioredis

            _client = aioredis.from_url(s.redis_url, socket_connect_timeout=1.0)
            await _client.ping()
        except Exception as exc:
            log.warning("Redis unavailable (%s); running without cache.", exc)
            _unavailable = True
            _client = None
    return _client


def make_key(kind: str, **parts: object) -> str:
    """Build a cache key.

    ``ENGINE_VERSION`` is in the key, not merely in ``meta``. Without it a
    backend redeploy that changes the geometry keeps serving the old numbers
    from cache -- which is the worst failure mode available here, because
    nothing looks wrong.
    """
    blob = orjson.dumps(parts, option=orjson.OPT_SORT_KEYS)
    digest = hashlib.sha256(blob).hexdigest()[:20]
    return f"pw:{ENGINE_VERSION}:s{PAYLOAD_SCHEMA}:{kind}:{digest}"


async def reset() -> None:
    """Drop the cached client so the next call reconnects.

    Called when an operation fails in a way that suggests the connection itself
    is broken rather than the request. Without it a single bad connection
    silently disables caching for the process lifetime -- the degradation is
    safe, but it is also invisible and permanent.
    """
    global _client, _unavailable
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
    _client = None
    _unavailable = False


async def get(key: str) -> dict[str, Any] | None:
    client = await get_client()
    if client is None:
        return None
    try:
        blob = await client.get(key)
    except Exception as exc:
        log.warning("cache read failed (%s)", exc)
        await reset()
        return None
    if not blob:
        return None
    try:
        decoded: dict[str, Any] = orjson.loads(_decompressor.decompress(blob))
        return decoded
    except Exception as exc:
        log.warning("cache entry unreadable, discarding (%s)", exc)
        return None


#: Every key this service writes starts with this, whatever the engine version.
NAMESPACE = "pw:"


async def count() -> int | None:
    """How many cached results there are; None when Redis is not in use."""
    client = await get_client()
    if client is None:
        return None
    n = 0
    try:
        async for _ in client.scan_iter(match=f"{NAMESPACE}*", count=500):
            n += 1
    except Exception as exc:
        log.warning("cache count failed (%s)", exc)
        await reset()
        return None
    return n


async def clear() -> int | None:
    """Delete every cached result, and only ours: never FLUSHDB on a shared Redis.

    Returns how many keys went; None when Redis is not in use.
    """
    client = await get_client()
    if client is None:
        return None
    deleted = 0
    batch: list[bytes] = []
    try:
        async for key in client.scan_iter(match=f"{NAMESPACE}*", count=500):
            batch.append(key)
            if len(batch) >= 500:
                deleted += int(await client.delete(*batch))
                batch = []
        if batch:
            deleted += int(await client.delete(*batch))
    except Exception as exc:
        log.warning("cache clear failed (%s)", exc)
        await reset()
    return deleted


async def put(key: str, value: dict[str, Any], ttl_s: int) -> None:
    client = await get_client()
    if client is None:
        return
    try:
        blob = _compressor.compress(orjson.dumps(value))
        await client.set(key, blob, ex=ttl_s)
    except Exception as exc:
        log.warning("cache write failed (%s)", exc)
        await reset()


async def single_flight(
    key: str, compute: Callable[[], Awaitable[dict[str, Any]]], ttl_s: int
) -> tuple[dict[str, Any], str]:
    """Return a cached value, or compute it once across concurrent callers.

    Returns ``(value, cache_state)`` where ``cache_state`` is "hit", "miss" or
    "bypass", which is reported verbatim in ``meta.cache``. Being able to see
    that in the network panel during a demo is worth the field.
    """
    cached = await get(key)
    if cached is not None:
        return cached, "hit"

    client = await get_client()
    if client is None:
        return await compute(), "bypass"

    lock_key = f"{key}:lock"
    try:
        acquired = await client.set(lock_key, b"1", nx=True, ex=30)
    except Exception:
        acquired = True

    if acquired:
        try:
            value = await compute()
            await put(key, value, ttl_s)
            return value, "miss"
        finally:
            try:
                await client.delete(lock_key)
            except Exception:
                pass

    # Lost the race: wait briefly for the winner rather than duplicating work.
    s = get_settings()
    deadline = asyncio.get_running_loop().time() + s.singleflight_wait_s
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.05)
        cached = await get(key)
        if cached is not None:
            return cached, "hit"
    # The winner is slower than we are willing to wait. Compute it ourselves
    # rather than fail: a duplicated computation is cheaper than a 500.
    return await compute(), "miss"
