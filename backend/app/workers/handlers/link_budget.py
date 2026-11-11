"""The downlink budget over each station pass (ADR-20): what the contact job adds when the
mission states its radio figures. Without them nothing here runs and the answer is line of
sight only, exactly as before.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from app.core import intervals, rf_link
from app.core.quantity import Provenance, Quantity
from app.core.spice import StationLook
from app.data.catalogues import GroundStation
from app.services import lifecycle

#: The published station figures are X-band: module 101 and 104's receive table.
X_BAND_MHZ = (8200.0, 8600.0)

NOT_MODELLED = (
    "Pointing loss (the spacecraft antenna's and the station's).",
    "Polarisation loss.",
    "The station's gain change with elevation (peak gain is used).",
    "DSN scheduling and load: when a station can hear, not whether it is booked.",
    "The uplink.",
)

FloatArray = npt.NDArray[np.float64]


def _q(
    value: float,
    unit: str,
    provenance: Provenance,
    *,
    source: str | None = None,
    lo: float | None = None,
    hi: float | None = None,
    why: str | None = None,
) -> dict[str, Any]:
    spread = lo is not None and hi is not None and not (lo == hi == value)
    return lifecycle.q(
        Quantity(
            value=value,
            unit=unit,
            provenance=provenance,
            lo=lo if spread else None,
            hi=hi if spread else None,
            no_margin_reason=None if spread else (why or "A stated figure, with no tolerance."),
            source=source,
        )
    )


def _given(li: dict[str, Any], key: str, unit: str, why: str) -> dict[str, Any]:
    v = float(li[key])
    return _q(v, unit, li["provenance"], source=li["source"], why=why)


def can_run(li: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Whether every input is stated, and what is missing otherwise."""
    li = li or {}
    miss = rf_link.missing_inputs(
        eirp_dbw=li.get("eirp_dbw"),
        frequency_mhz=li.get("frequency_mhz"),
        required_ebn0_db=li.get("required_ebn0_db"),
    )
    return (not miss), miss


def _receiver(g: GroundStation) -> rf_link.Receiver | None:
    rx, atm = g.rx_x, g.atmosphere_x
    if rx is None or atm is None:
        return None
    return rf_link.Receiver(
        gain_dbi=rx.gain_dbi,
        gain_tol_adverse_db=rx.gain_tol_adverse_db,
        gain_tol_favourable_db=rx.gain_tol_favourable_db,
        t_amw_k=rx.t_amw_k,
        t_amw_tol_adverse_k=rx.t_amw_tol_adverse_k,
        t_amw_tol_favourable_k=rx.t_amw_tol_favourable_k,
        zenith_clear_db=atm.zenith_clear_db,
        zenith_adverse_db=atm.zenith_adverse_db,
    )


def _point(
    b: rf_link.Budget, i: int, li: dict[str, Any], at: Literal["edge", "peak"]
) -> dict[str, Any]:
    rates = [float(r) for r in li.get("data_rates_kbps") or []]
    geom = "From the station kernel's geometry; the DSN mask sets the edge without a tolerance."
    return {
        "at": at,
        "elevation_deg": _q(float(b.elevation_deg[i]), "deg", "computed", why=geom),
        "range_km": _q(float(b.range_km[i]), "km", "computed", why=geom),
        "path_loss_db": _q(
            float(b.fspl_db[i]), "dB", "computed", why="Free-space loss from range and frequency."
        ),
        "atmosphere_db": lifecycle.q(rf_link.quantity(b.atmosphere_db, i, "dB")),
        "g_over_t_dbk": lifecycle.q(rf_link.quantity(b.g_over_t_dbk, i, "dB/K")),
        "max_rate_kbps": lifecycle.q(
            rf_link.quantity(rf_link.max_rate_bps(b), i, "kbit/s", scale=1e-3)
        ),
        "margins": [
            {
                "rate_kbps": _given(
                    {**li, "r": r}, "r", "kbit/s", "A rate as stated; it carries no tolerance."
                ),
                "margin_db": lifecycle.q(rf_link.quantity(rf_link.margin_db(b, r * 1e3), i, "dB")),
            }
            for r in rates
        ],
    }


def _points(
    b: rf_link.Budget, li: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], FloatArray]:
    rate = rf_link.max_rate_bps(b).value
    n = len(rate)
    peak = int(np.argmax(b.elevation_deg))
    # The weakest end of the pass: the end sample with the lower achievable rate.
    edge = 0 if rate[0] <= rate[n - 1] else n - 1
    return _point(b, edge, li, "edge"), _point(b, peak, li, "peak"), rate


def stations(
    li: dict[str, Any],
    stations_: list[GroundStation],
    looks: list[StationLook],
    t_s: FloatArray,
    heard_by: dict[str, list[intervals.Run]],
) -> dict[str, dict[str, Any]]:
    """Per station id: ``passes`` (one per heard stretch, in order) and the best ``summary``."""
    tx = rf_link.Transmitter(
        eirp_dbw=float(li["eirp_dbw"]),
        frequency_ghz=float(li["frequency_mhz"]) / 1e3,
        required_ebn0_db=float(li["required_ebn0_db"]),
        eirp_tol_db=float(li.get("eirp_tol_db") or 0.0),
        required_margin_db=float(li.get("required_margin_db") or 0.0),
    )
    out: dict[str, dict[str, Any]] = {}
    for g, look in zip(stations_, looks, strict=True):
        rx = _receiver(g)
        if rx is None:
            continue
        passes: list[dict[str, Any]] = []
        best: tuple[float, dict[str, Any]] | None = None
        for run in heard_by[g.id]:
            if not run.value:
                continue
            eps = intervals.EPS_S
            sel = np.flatnonzero((t_s >= run.start - eps) & (t_s <= run.end + eps))
            if sel.size == 0:
                sel = np.array([int(np.argmin(np.abs(t_s - 0.5 * (run.start + run.end))))])
            b = rf_link.evaluate(look.range_m[sel] / 1e3, look.el_deg[sel], rx, tx)
            edge, peak, rate = _points(b, li)
            p = {"edge": edge, "peak": peak}
            passes.append(p)
            top = float(rate.max())
            if best is None or top > best[0]:
                best = (top, peak)
        out[g.id] = {
            "passes": passes,
            "best_rate": None if best is None else best[1]["max_rate_kbps"],
            "best_margin": None
            if best is None or not best[1]["margins"]
            else best[1]["margins"][0]["margin_db"],
        }
    return out


def basis(li: dict[str, Any], stations_: list[GroundStation]) -> dict[str, Any]:
    """What the budget ran on, each figure with its provenance."""
    eirp = float(li["eirp_dbw"])
    tol = li.get("eirp_tol_db")
    if tol:
        eirp_q = _q(
            eirp,
            "dBW",
            li["provenance"],
            source=li["source"],
            lo=eirp - float(tol),
            hi=eirp + float(tol),
        )
    else:
        eirp_q = _given(li, "eirp_dbw", "dBW", "No tolerance is stated for the lander's EIRP.")
    margin = li.get("required_margin_db")
    if margin is None:
        margin_q = _q(
            0.0,
            "dB",
            "assumed",
            why="No margin is entered, so the rate is the highest that just closes the link.",
        )
    else:
        margin_q = _given(li, "required_margin_db", "dB", "A margin as stated.")
    rows = []
    without = []
    for g in stations_:
        rx, atm = g.rx_x, g.atmosphere_x
        if rx is None or atm is None:
            without.append(g.id)
            continue
        rows.append(
            {
                "id": g.id,
                "configuration": rx.configuration,
                "gain_dbi": _q(
                    rx.gain_dbi,
                    "dBi",
                    "published",
                    source=rx.source_url,
                    lo=rx.gain_dbi - rx.gain_tol_adverse_db,
                    hi=rx.gain_dbi + rx.gain_tol_favourable_db,
                ),
                "t_amw_k": _q(
                    rx.t_amw_k,
                    "K",
                    "published",
                    source=rx.source_url,
                    lo=rx.t_amw_k - rx.t_amw_tol_favourable_k,
                    hi=rx.t_amw_k + rx.t_amw_tol_adverse_k,
                ),
                "zenith_clear_db": _q(
                    atm.zenith_clear_db,
                    "dB",
                    "published",
                    source=atm.source_url,
                    why="A tabulated 25 % point of the handbook's record.",
                ),
                "zenith_adverse_db": _q(
                    atm.zenith_adverse_db,
                    "dB",
                    "published",
                    source=atm.source_url,
                    why="A tabulated 99 % point of the handbook's record.",
                ),
                "module": f"{rx.module}; {atm.module}",
                "source_urls": [rx.source_url, atm.source_url],
            }
        )
    return {
        "method": rf_link.METHOD,
        "band": "X",
        "frequency_mhz": _given(li, "frequency_mhz", "MHz", "A frequency as stated."),
        "eirp_dbw": eirp_q,
        "required_ebn0_db": _given(
            li, "required_ebn0_db", "dB", "The coding's requirement as stated, with no tolerance."
        ),
        "required_margin_db": margin_q,
        "stated_rates_kbps": [
            _given({**li, "r": r}, "r", "kbit/s", "A rate as stated.")
            for r in li.get("data_rates_kbps") or []
        ],
        "stations": rows,
        "stations_without_figures": without,
        "not_modelled": list(NOT_MODELLED),
    }


def ran_note(li: dict[str, Any], b: dict[str, Any]) -> str:
    who = "published" if li["provenance"] == "published" else "entered"
    f = float(li["frequency_mhz"])
    text = (
        f"Link budget on the lander's {float(li['eirp_dbw']):.1f} dBW EIRP, {f:.0f} MHz and a "
        f"required Eb/N0 of {float(li['required_ebn0_db']):.1f} dB (all {who}: {li['source']}), "
        "with each DSN antenna's gain, noise and atmosphere from the handbook 810-005 modules "
        "101, 104 and 105. The data rate is the highest that keeps "
        f"{float(li.get('required_margin_db') or 0.0):.1f} dB over the required Eb/N0; the "
        "range runs from clear sky to the 99 % weather point. Pointing and polarisation loss "
        "and DSN scheduling are not modelled."
    )
    if b["stations_without_figures"]:
        text += (
            " No published X-band figures for "
            + ", ".join(s.upper() for s in b["stations_without_figures"])
            + ", so no budget is given there."
        )
    return text


def off_band_note(li: dict[str, Any]) -> str:
    return (
        f"Line of sight only: the published station figures are X-band "
        f"({X_BAND_MHZ[0]:.0f} to {X_BAND_MHZ[1]:.0f} MHz) and the stated frequency is "
        f"{float(li['frequency_mhz']):.0f} MHz, so no data rate or link margin is given."
    )
