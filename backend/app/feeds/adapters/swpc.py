"""NOAA Space Weather Prediction Center (SWPC) JSON and text products.

Addresses and formats as served on 2026-09-26 (fixtures recorded that day):

* ``products/noaa-planetary-k-index.json``: the *new* format, a list of
  objects ``{time_tag, Kp, a_running, station_count}``. The old list-of-lists
  layout is refused with a clear error rather than misread.
* ``products/noaa-planetary-k-index-forecast.json``: ``{time_tag, kp,
  observed, noaa_scale}`` with ``observed`` one of observed/estimated/predicted.
* ``json/goes/primary/integral-protons-6-hour.json`` and ``xrays-6-hour.json``.
* ``json/rtsw/rtsw_wind_1m.json`` and ``rtsw_mag_1m.json``: real-time solar
  wind from several spacecraft at once; only rows flagged ``active: true`` are
  the ones SWPC itself uses, so only those are kept.
* ``products/alerts.json`` and ``text/3-day-forecast.txt`` (kept verbatim; its
  proton-event probabilities are quoted, never recomputed).
* ``json/f107_cm_flux.json``: 10.7 cm solar radio flux, for air drag.

Public domain (US government). Units: SI where one applies (m/s, K, T,
W/m^2); particle flux stays in pfu (particles cm^-2 s^-1 sr^-1), the unit
every alert threshold is written in.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.feeds.base import (
    PUBLIC_DOMAIN,
    Parsed,
    ParseError,
    Product,
    ProviderSpec,
    in_range,
    iso,
    utc,
)

BASE = "https://services.swpc.noaa.gov"
PROVIDER = ProviderSpec(name="swpc", capacity=30, per_hour=240)
LICENCE = f"NOAA SWPC, {PUBLIC_DOMAIN}"

#: How much of each series is kept in ``parsed``: enough to show a trend
#: without copying the whole body again.
SERIES_HOURS = 6


def _json(body: bytes) -> Any:
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ParseError(f"not JSON: {exc}") from exc


def _rows(body: bytes) -> list[dict[str, Any]]:
    data = _json(body)
    if not isinstance(data, list) or (data and not isinstance(data[0], dict)):
        raise ParseError(
            "expected a list of objects (SWPC's current format); got "
            + (type(data[0]).__name__ if isinstance(data, list) and data else type(data).__name__)
        )
    return data


# --- Kp ---------------------------------------------------------------------


def parse_kp(body: bytes) -> Parsed:
    rows = _rows(body)
    issues: list[str] = []
    series = []
    for r in rows:
        if "time_tag" not in r or "Kp" not in r:
            raise ParseError("Kp rows need time_tag and Kp")
        kp = in_range("Kp", r["Kp"], 0.0, 9.0, issues)
        if kp is None:
            continue
        series.append({"t": iso(utc(r["time_tag"])), "kp": kp, "stations": r.get("station_count")})
    if not series:
        raise ParseError("no usable Kp values")
    last = series[-1]
    return Parsed(
        values={"latest": last, "series": series},
        issued_at=utc(str(last["t"])),
        valid_from=utc(str(series[0]["t"])),
        valid_to=utc(str(last["t"])) + timedelta(hours=3),
        issues=issues,
    )


def parse_kp_forecast(body: bytes) -> Parsed:
    rows = _rows(body)
    issues: list[str] = []
    series = []
    for r in rows:
        kp = in_range("kp", r.get("kp"), 0.0, 9.0, issues)
        if kp is None or "time_tag" not in r:
            continue
        series.append({"t": iso(utc(r["time_tag"])), "kp": kp, "kind": r.get("observed")})
    predicted = [s for s in series if s["kind"] == "predicted"]
    if not series:
        raise ParseError("no usable Kp forecast values")
    observed = [s for s in series if s["kind"] != "predicted"]
    issued = utc(str((observed or series)[-1]["t"]))
    return Parsed(
        values={"series": series, "predicted_max": max((p["kp"] for p in predicted), default=None)},
        issued_at=issued,
        valid_from=utc(str(series[0]["t"])),
        valid_to=utc(str(series[-1]["t"])) + timedelta(hours=3),
        issues=issues,
    )


# --- GOES protons and X-rays -------------------------------------------------


def _recent(series: list[dict[str, Any]], hours: float) -> list[dict[str, Any]]:
    if not series:
        return series
    end = utc(str(series[-1]["t"]))
    return [s for s in series if utc(str(s["t"])) >= end - timedelta(hours=hours)]


def parse_protons(body: bytes) -> Parsed:
    rows = _rows(body)
    issues: list[str] = []
    by: dict[str, list[dict[str, Any]]] = {}
    sats: set[int] = set()
    for r in rows:
        energy = r.get("energy")
        if not isinstance(energy, str) or "time_tag" not in r:
            raise ParseError("proton rows need energy and time_tag")
        flux = in_range(f"flux {energy}", r.get("flux"), 0.0, 1e7, issues)
        if flux is None:
            continue
        if isinstance(r.get("satellite"), int):
            sats.add(r["satellite"])
        by.setdefault(energy, []).append({"t": iso(utc(r["time_tag"])), "pfu": flux})
    for key in (">=10 MeV", ">=100 MeV"):
        if key not in by:
            raise ParseError(f"no {key} channel")
    latest = {e: s[-1] for e, s in by.items()}
    last_t = max(utc(str(v["t"])) for v in latest.values())
    return Parsed(
        values={
            "unit": "pfu",
            "satellites": sorted(sats),
            "latest": latest,
            "series": {
                e: _recent(s, SERIES_HOURS) for e, s in by.items() if e in (">=10 MeV", ">=100 MeV")
            },
        },
        issued_at=last_t,
        valid_from=min(utc(str(s[0]["t"])) for s in by.values()),
        valid_to=last_t,
        issues=issues,
    )


def xray_class(flux_w_m2: float) -> str:
    """GOES 0.1-0.8 nm flux as a flare class: A1.0 ... X10."""
    for letter, base in (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8)):
        if flux_w_m2 >= base:
            return f"{letter}{flux_w_m2 / base:.1f}"
    return f"A{flux_w_m2 / 1e-8:.1f}"


def parse_xrays(body: bytes) -> Parsed:
    rows = _rows(body)
    issues: list[str] = []
    long_band: list[dict[str, Any]] = []
    for r in rows:
        if r.get("energy") != "0.1-0.8nm":
            continue
        flux = in_range("x-ray flux", r.get("flux"), 1e-10, 1e-1, issues)
        if flux is None:
            continue
        long_band.append({"t": iso(utc(r["time_tag"])), "w_m2": flux})
    if not long_band:
        raise ParseError("no 0.1-0.8 nm X-ray values")
    peak = max(long_band, key=lambda s: s["w_m2"])
    last = long_band[-1]
    return Parsed(
        values={
            "unit": "W/m^2",
            "latest": {**last, "class": xray_class(float(last["w_m2"]))},
            "peak_6h": {**peak, "class": xray_class(float(peak["w_m2"]))},
        },
        issued_at=utc(str(last["t"])),
        valid_from=utc(str(long_band[0]["t"])),
        valid_to=utc(str(last["t"])),
        issues=issues,
    )


# --- real-time solar wind ------------------------------------------------------


def _active(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if rows and "active" not in rows[0]:
        raise ParseError("real-time solar wind rows have no 'active' flag")
    act = [r for r in rows if r.get("active") is True]
    return sorted(act, key=lambda r: str(r.get("time_tag")))


def parse_rtsw_wind(body: bytes) -> Parsed:
    rows = _active(_rows(body))
    issues: list[str] = []
    series = []
    for r in rows:
        v = in_range("proton_speed", r.get("proton_speed"), 100.0, 3500.0, issues)
        n = in_range("proton_density", r.get("proton_density"), 0.0, 500.0, issues)
        temp = in_range("proton_temperature", r.get("proton_temperature"), 1e3, 1e8, issues)
        if v is None and n is None:
            continue
        series.append(
            {
                "t": iso(utc(r["time_tag"])),
                "speed_m_s": None if v is None else v * 1000.0,
                "density_m3": None if n is None else n * 1e6,
                "temperature_k": temp,
                "source": r.get("source"),
            }
        )
    if not series:
        raise ParseError("no active solar wind rows")
    keep = _recent(series, SERIES_HOURS)
    return Parsed(
        values={
            "latest": keep[-1],
            "series": keep[::5],
            "sources": sorted({str(s["source"]) for s in keep}),
        },
        issued_at=utc(str(keep[-1]["t"])),
        valid_from=utc(str(keep[0]["t"])),
        valid_to=utc(str(keep[-1]["t"])),
        issues=issues[:20] + ([f"... {len(issues) - 20} more"] if len(issues) > 20 else []),
    )


def parse_rtsw_mag(body: bytes) -> Parsed:
    rows = _active(_rows(body))
    issues: list[str] = []
    series = []
    for r in rows:
        bt = in_range("bt", r.get("bt"), 0.0, 500.0, issues)
        bz = in_range("bz_gsm", r.get("bz_gsm"), -500.0, 500.0, issues)
        if bt is None and bz is None:
            continue
        series.append(
            {
                "t": iso(utc(r["time_tag"])),
                "bt_t": None if bt is None else bt * 1e-9,
                "bz_gsm_t": None if bz is None else bz * 1e-9,
                "source": r.get("source"),
            }
        )
    if not series:
        raise ParseError("no active magnetic field rows")
    keep = _recent(series, SERIES_HOURS)
    return Parsed(
        values={"latest": keep[-1], "series": keep[::5]},
        issued_at=utc(str(keep[-1]["t"])),
        valid_from=utc(str(keep[0]["t"])),
        valid_to=utc(str(keep[-1]["t"])),
        issues=issues[:20],
    )


# --- alerts, the 3-day forecast, F10.7 ----------------------------------------


def parse_alerts(body: bytes) -> Parsed:
    rows = _rows(body)
    out = []
    for r in rows:
        if "message" not in r or "issue_datetime" not in r:
            raise ParseError("alert rows need message and issue_datetime")
        msg = str(r["message"]).replace("\r\n", "\n")
        headline = next(
            (
                ln.strip()
                for ln in msg.splitlines()
                if ln.startswith(("ALERT", "WARNING", "WATCH", "SUMMARY", "EXTENDED", "CANCEL"))
            ),
            msg.splitlines()[0] if msg else "",
        )
        out.append(
            {
                "product_id": r.get("product_id"),
                "issued": iso(utc(str(r["issue_datetime"]))),
                "headline": headline,
                "message": msg[:2000],
            }
        )
    out.sort(key=lambda a: str(a["issued"]), reverse=True)
    issued = utc(str(out[0]["issued"])) if out else None
    return Parsed(values={"alerts": out[:50]}, issued_at=issued)


_ISSUED = re.compile(r":Issued:\s+(\d{4}) (\w{3}) (\d{1,2}) (\d{2})(\d{2}) UTC")
_S1 = re.compile(r"S1 or greater\s+(\d+)%\s+(\d+)%\s+(\d+)%")
_R12 = re.compile(r"R1-R2\s+(\d+)%\s+(\d+)%\s+(\d+)%")
_R3 = re.compile(r"R3 or greater\s+(\d+)%\s+(\d+)%\s+(\d+)%")
_KPMAX = re.compile(r"greatest expected 3 hr Kp for ([^\n]+?) is ([\d.]+)")


def parse_3day(body: bytes) -> Parsed:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("3-day forecast is not text") from exc
    m = _ISSUED.search(text)
    if not m or "3-Day Forecast" not in text:
        raise ParseError("not an SWPC 3-day forecast (no ':Issued:' line)")
    issued = datetime.strptime(
        f"{m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}{m.group(5)}", "%Y %b %d %H%M"
    ).replace(tzinfo=UTC)

    def pct(rx: re.Pattern[str]) -> list[int] | None:
        mm = rx.search(text)
        return None if mm is None else [int(mm.group(i)) for i in (1, 2, 3)]

    kp = _KPMAX.search(text)
    return Parsed(
        values={
            "text": text,
            "s1_or_greater_pct": pct(_S1),
            "r1_r2_pct": pct(_R12),
            "r3_or_greater_pct": pct(_R3),
            "kp_max_expected": float(kp.group(2)) if kp else None,
            "days": kp.group(1).strip() if kp else None,
        },
        issued_at=issued,
        valid_from=issued,
        valid_to=issued + timedelta(days=3),
    )


def parse_f107(body: bytes) -> Parsed:
    rows = _rows(body)
    issues: list[str] = []
    vals = []
    for r in rows:
        f = in_range("f10.7", r.get("flux"), 30.0, 600.0, issues)
        if f is None or "time_tag" not in r:
            continue
        vals.append(
            {"t": iso(utc(r["time_tag"])), "sfu": f, "schedule": r.get("reporting_schedule")}
        )
    if not vals:
        raise ParseError("no usable F10.7 values")
    vals.sort(key=lambda v: str(v["t"]))
    return Parsed(
        values={"unit": "sfu", "latest": vals[-1], "series": vals[-90:]},
        issued_at=utc(str(vals[-1]["t"])),
        issues=issues,
    )


def products() -> list[Product]:
    def p(
        product: str, path: str, parse: Any, interval_s: int, staleness_s: int, v: str
    ) -> Product:
        return Product(
            provider="swpc",
            product=product,
            url=f"{BASE}/{path}",
            licence=LICENCE,
            parser_version=v,
            interval_s=interval_s,
            staleness_s=staleness_s,
            parse=parse,
        )

    return [
        p("kp", "products/noaa-planetary-k-index.json", parse_kp, 900, 6 * 3600, "kp-2"),
        p(
            "kp_forecast",
            "products/noaa-planetary-k-index-forecast.json",
            parse_kp_forecast,
            3600,
            12 * 3600,
            "kpf-1",
        ),
        p(
            "goes_protons",
            "json/goes/primary/integral-protons-6-hour.json",
            parse_protons,
            300,
            3600,
            "prot-1",
        ),
        p("goes_xrays", "json/goes/primary/xrays-6-hour.json", parse_xrays, 300, 3600, "xray-1"),
        p("rtsw_wind", "json/rtsw/rtsw_wind_1m.json", parse_rtsw_wind, 900, 3 * 3600, "rtsw-1"),
        p("rtsw_mag", "json/rtsw/rtsw_mag_1m.json", parse_rtsw_mag, 900, 3 * 3600, "rtsw-1"),
        p("alerts", "products/alerts.json", parse_alerts, 900, 6 * 3600, "alerts-1"),
        p("forecast_3day", "text/3-day-forecast.txt", parse_3day, 3 * 3600, 36 * 3600, "3day-1"),
        p("f107", "json/f107_cm_flux.json", parse_f107, 6 * 3600, 48 * 3600, "f107-1"),
    ]
