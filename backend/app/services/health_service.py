"""Liveness and readiness, assembled where the dependencies are known.

The route used to reach into ``core.spice`` and the filesystem itself. Keeping
the probe here means the HTTP layer only serialises a verdict, and the rule the
verdict follows is written down once:

* **down** (503) -- no ephemeris or no database. Without either there is no
  product to serve.
* **degraded** (200) -- the regional elevation model or Redis is missing. Every
  ephemeris endpoint still works and the UI has a state for partial data, so
  failing the check would take the demo down for a condition already handled.
* **ok** -- everything present.

Live feeds (ADR-8) can make the service *degraded*, never *down*: a provider
that is failing is reported in the ``feeds`` block and the numbers it feeds
say why they are missing, while everything else keeps working. Stale data
alone does not degrade the service (each number already says its age).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ENGINE_VERSION, get_settings
from app.core import spice
from app.core.kernels import missing as missing_kernels
from app.services import cache, feed_service, site_service


async def report(session: AsyncSession) -> tuple[int, dict[str, Any]]:
    """``(http_status, body)`` for ``/healthz``."""
    s = get_settings()
    ks = spice.state()
    db_ok = await site_service.database_is_reachable(session)
    try:
        redis_ok = (await cache.get_client()) is not None
    except Exception:
        redis_ok = False

    dem_present = s.regional_dem_path.exists()
    fine_dir = s.dem_dir / "fine"
    fine_count = len(list(fine_dir.glob("*.npz"))) if fine_dir.exists() else 0

    feeds: dict[str, int] = {"ok": 0, "stale": 0, "failing": 0}
    if db_ok:
        try:
            feeds = await feed_service.summary(session)
        except Exception:  # a missing feeds table must not take health down
            feeds = {"ok": 0, "stale": 0, "failing": 0}

    if not ks.loaded or not db_ok:
        status, code = "down", 503
    elif not dem_present or not redis_ok or feeds["failing"] > 0:
        status, code = "degraded", 200
    else:
        status, code = "ok", 200

    return code, {
        "status": status,
        "engine_version": ENGINE_VERSION,
        "kernels": {
            "loaded": ks.loaded,
            "count": ks.count,
            "furnsh_ms": round(ks.furnsh_ms, 1),
            "missing": ks.missing or missing_kernels(s.kernel_dir),
            "error": ks.error,
        },
        "db": "ok" if db_ok else "down",
        "redis": "ok" if redis_ok else "bypass",
        "feeds": feeds,
        "dem": {
            "regional_present": dem_present,
            "fine_windows": fine_count,
            "product": "LOLA LDEM 80S (PDS Geosciences Node)",
        },
    }
