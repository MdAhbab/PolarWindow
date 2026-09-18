"""Liveness and readiness.

Returns **200 when degraded** and 503 only when SPICE is unloaded. That split is
deliberate: a missing DEM still leaves every ephemeris endpoint working and the
UI has a state for partial data, so failing the whole check for a partial
capability would take the demo down for a condition the product already handles.
A missing ephemeris is different -- without it there are no Sun or Earth
positions at all, which is the product.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response

from app.api.v1.deps import db, settings
from app.api.v1.schemas.health import HealthResponse
from app.config import ENGINE_VERSION, Settings
from app.core import spice
from app.core.kernels import missing as missing_kernels

router = APIRouter(tags=["health"])


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness plus kernel-loaded check",
)
async def healthz(
    response: Response,
    session: Any = Depends(db),
    s: Settings = Depends(settings),
) -> dict[str, Any]:
    ks = spice.state()

    from app.services.site_service import database_is_reachable

    db_ok = await database_is_reachable(session)

    redis_ok = False
    try:
        from app.services.cache import get_client

        client = await get_client()
        redis_ok = client is not None
    except Exception:
        redis_ok = False

    dem_present = s.regional_dem_path.exists()
    fine_count = len(list((s.dem_dir / "fine").glob("*.npz"))) if s.dem_dir.exists() else 0

    if not ks.loaded or not db_ok:
        status = "down"
        response.status_code = 503
    elif not dem_present or not redis_ok:
        status = "degraded"
    else:
        status = "ok"

    return {
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
        "dem": {
            "regional_present": dem_present,
            "fine_windows": fine_count,
            "product": "LOLA LDEM 80S (PDS Geosciences Node)",
        },
    }
