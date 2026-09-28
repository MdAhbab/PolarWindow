"""Space weather now (plan track E): what NOAA SWPC and NASA DONKI report, as recorded
by the feeds worker. Nothing here is a dose: it says what the Sun is doing, how old each
reading is, and SWPC's own three-day proton outlook word for word."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.quantity import Quantity
from app.services import feed_service, lifecycle

SWPC = "NOAA Space Weather Prediction Center"
DONKI = "NASA DONKI (CCMC)"


def _pub(latest: feed_service.Latest, value: float | None, unit: str) -> dict[str, Any]:
    if value is None or latest.snapshot is None or latest.values is None:
        return lifecycle.missing(unit, latest.missing_reason or "Not recorded yet.")
    return lifecycle.q(
        Quantity(
            value=float(value),
            unit=unit,
            provenance="published",
            no_margin_reason=f"As {SWPC} reports it.",
            source=latest.snapshot.url,
        )
    )


def _events(latest: feed_service.Latest, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{k: e.get(k) for k in keys} for e in ((latest.values or {}).get("events") or [])[:20]]


async def now(session: AsyncSession) -> dict[str, Any]:
    got = {
        name: await feed_service.latest(session, provider, product)
        for name, provider, product in (
            ("kp", "swpc", "kp"),
            ("protons", "swpc", "goes_protons"),
            ("xrays", "swpc", "goes_xrays"),
            ("wind", "swpc", "rtsw_wind"),
            ("mag", "swpc", "rtsw_mag"),
            ("alerts", "swpc", "alerts"),
            ("outlook", "swpc", "forecast_3day"),
            ("cme", "donki", "cme"),
            ("flr", "donki", "flr"),
            ("sep", "donki", "sep"),
        )
    }
    kp = (got["kp"].values or {}).get("latest") or {}
    prot = (got["protons"].values or {}).get("latest") or {}
    xr = (got["xrays"].values or {}).get("latest") or {}
    wind = (got["wind"].values or {}).get("latest") or {}
    mag = (got["mag"].values or {}).get("latest") or {}
    speed = wind.get("speed_m_s")
    bz = mag.get("bz_gsm_t")
    t_now = datetime.now(UTC)
    alerts = [
        a.get("headline") or ""
        for a in (got["alerts"].values or {}).get("alerts") or []
        if a.get("issued") and t_now - lifecycle.parse_time(a["issued"]) < timedelta(hours=24)
    ]
    ov = got["outlook"].values
    outlook = {
        "issued": None if got["outlook"].snapshot is None else got["outlook"].snapshot.issued_at,
        "days": None if ov is None else ov.get("days"),
        "s1_or_greater_pct": None if ov is None else ov.get("s1_or_greater_pct"),
        "kp_max_expected": None if ov is None else ov.get("kp_max_expected"),
        "text": None if ov is None else ov.get("text"),
        "missing_reason": None if ov is not None else got["outlook"].missing_reason,
    }
    donki_missing = next(
        (got[k].missing_reason for k in ("cme", "flr", "sep") if got[k].values is None), None
    )
    data = {
        "now": {
            "kp": _pub(got["kp"], kp.get("kp"), "Kp"),
            "proton_10mev_pfu": _pub(
                got["protons"], (prot.get(">=10 MeV") or {}).get("pfu"), "pfu"
            ),
            "proton_100mev_pfu": _pub(
                got["protons"], (prot.get(">=100 MeV") or {}).get("pfu"), "pfu"
            ),
            "xray_class": xr.get("class"),
            "solar_wind_km_s": _pub(got["wind"], None if speed is None else speed / 1000.0, "km/s"),
            "bz_nt": _pub(got["mag"], None if bz is None else bz * 1e9, "nT"),
            "alerts": [h for h in alerts if h],
        },
        "outlook": outlook,
        "donki": {
            "cme": _events(
                got["cme"], ("id", "start", "speed_m_s", "earth_arrival_estimates", "link")
            ),
            "flares": _events(got["flr"], ("id", "peak", "class", "link")),
            "sep": _events(got["sep"], ("id", "time", "instruments", "link")),
            "days": int((got["sep"].values or {}).get("days") or 0) or None,
            "missing_reason": donki_missing,
        },
        "note": "What the Sun is doing now, as NOAA SWPC and NASA DONKI report it; each number "
        "has its own age. Doses along a trip are in the Trip section, as a screening estimate.",
    }
    used = [(k, v) for k, v in got.items() if v.snapshot is not None]
    sources = [
        ref
        for k, v in used
        if (ref := v.source_ref(DONKI if k in ("cme", "flr", "sep") else SWPC)) is not None
    ]
    stale = any(v.stale for v in got.values() if v.snapshot is not None)
    newest = max((feed_service.data_time(v.snapshot) for _, v in used), default=None)  # type: ignore[arg-type]
    return {
        "data": data,
        "meta": lifecycle.meta(
            engines=("rad",),
            sources=sources,
            parts=[("Space weather", "As published; no model of ours is involved.")],
            stale=stale,
            computed_at=newest,
        ),
    }
