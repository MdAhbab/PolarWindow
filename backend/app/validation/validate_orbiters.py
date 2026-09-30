"""Real orbiters' passes over landing sites against JPL Horizons (plan track T1, F2).

Run: ``make validate-orbiters`` (or ``uv run python -m app.validation.validate_orbiters``).
Needs the network (JPL Horizons, about 30 requests). Prints the docs/validation.md
table and writes ``data/contact/orbiters_check.json`` (committed).

For each landed CLPS site and each orbiter (LRO, Danuri, Chandrayaan-2, CAPSTONE):

* The trajectory the product uses: Horizons VECTORS every 5 minutes, Moon-centred
  ICRF, parsed by the feeds adapter and written as an SPK type 13 kernel.
* Azimuth and elevation from the site (on the 1737.4 km sphere, as Horizons
  places a lunar site at height 0), with the light time and aberration seen
  from the site (CSPICE ``spkcpo``), against Horizons' own observer table
  ("airless apparent" azimuth and elevation, Moon mean-Earth frame) every
  minute while the orbiter is up. The plan asks for 0.02 deg.
* Rise and set over the flat horizon (angular radius 0): ours from a 30 s
  grid refined by bisection, as the Contact answer does over the skyline;
  Horizons' from its table every 2 seconds, interpolated. The plan asks for 2 s.

And one check against NAIF's own LRO reconstruction (``lrorg_2025074_2025166``,
in data/validation/lro): the same azimuth and elevation from that kernel,
where the plan asks for 0.01 deg (its WebGeocalc tolerance).
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from app.config import get_settings
from app.core import intervals, spice, visibility
from app.feeds.adapters import horizons

R_KM = 1737.4
HZ = horizons.URL


@dataclass(frozen=True)
class Case:
    site: str
    lat: float
    lon: float
    start: datetime
    end: datetime


CASES = [
    Case(
        "IM-2 (Athena, Mons Mouton)",
        -84.7906,
        29.1957,
        datetime(2025, 3, 6, 17, 30, tzinfo=UTC),
        datetime(2025, 3, 7, 6, 15, tzinfo=UTC),
    ),
    Case(
        "IM-1 (Odysseus, Malapert A)",
        -80.13,
        1.44,
        datetime(2024, 2, 23, 0, 0, tzinfo=UTC),
        datetime(2024, 2, 23, 12, 0, tzinfo=UTC),
    ),
    Case(
        "Blue Ghost 1 (Mare Crisium)",
        18.5623,
        61.8103,
        datetime(2025, 3, 3, 0, 0, tzinfo=UTC),
        datetime(2025, 3, 3, 12, 0, tzinfo=UTC),
    ),
]
ORBITERS = [("lro", -85), ("danuri", -155), ("chandrayaan-2-orbiter", -152), ("capstone", -1176)]
NAIF_LRO = Case(
    "IM-2 site, LRO from NAIF's reconstruction",
    -84.7906,
    29.1957,
    datetime(2025, 4, 1, 0, 0, tzinfo=UTC),
    datetime(2025, 4, 1, 12, 0, tzinfo=UTC),
)


def _get(client: httpx.Client, params: dict[str, str]) -> str:
    for attempt in range(4):
        r = client.get(HZ, params=params, timeout=180)
        if r.status_code == 200:
            time.sleep(1.0)
            return r.text
        time.sleep(5.0 * (attempt + 1))
    r.raise_for_status()
    return r.text


def observer_table(client: httpx.Client, naif: int, c: Case, intervals_n: int) -> np.ndarray:
    """``(n, 3)``: seconds from ``c.start`` (UTC), azimuth, elevation (deg)."""
    text = _get(
        client,
        {
            "format": "text",
            "COMMAND": f"'{naif}'",
            "OBJ_DATA": "'NO'",
            "MAKE_EPHEM": "'YES'",
            "EPHEM_TYPE": "'OBSERVER'",
            "CENTER": "'coord@301'",
            "COORD_TYPE": "'GEODETIC'",
            "SITE_COORD": f"'{c.lon % 360.0:.6f},{c.lat:.6f},0'",
            "START_TIME": f"'{c.start:%Y-%m-%d %H:%M}'",
            "STOP_TIME": f"'{c.end:%Y-%m-%d %H:%M}'",
            "STEP_SIZE": f"'{intervals_n}'",
            "QUANTITIES": "'4'",
            "ANG_FORMAT": "'DEG'",
            "EXTRA_PREC": "'YES'",
            "CSV_FORMAT": "'YES'",
            "APPARENT": "'AIRLESS'",
            "TIME_DIGITS": "'FRACSEC'",
        },
    )
    if "$$SOE" not in text:
        raise RuntimeError(text[:400])
    if "MEAN_ME" not in text.split("$$SOE")[0]:
        raise RuntimeError("Horizons did not place the site in the Moon's mean-Earth frame")
    rows = []
    for line in text.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines():
        f = [x.strip() for x in line.split(",")]
        t = datetime.strptime(f[0], "%Y-%b-%d %H:%M:%S.%f").replace(tzinfo=UTC)
        rows.append(((t - c.start).total_seconds(), float(f[3]), float(f[4])))
    return np.array(rows)


def vectors(client: httpx.Client, naif: int, c: Case) -> dict[str, Any]:
    p = horizons.params(naif, c.start - timedelta(hours=1), c.end + timedelta(hours=1))
    return horizons.parse(_get(client, p).encode()).values


def our_look(target: str, c: Case, t0_et: float, ts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    site = visibility.site_position(c.lat, c.lon, R_KM * 1000.0)
    v = spice.site_look(target, site, t0_et + ts)
    return visibility.look_angles(visibility.enu_basis(c.lat, c.lon), v)


def separation_deg(
    az1: np.ndarray, el1: np.ndarray, az2: np.ndarray, el2: np.ndarray
) -> np.ndarray:
    a1, e1, a2, e2 = (np.radians(x) for x in (az1, el1, az2, el2))
    cosd = np.sin(e1) * np.sin(e2) + np.cos(e1) * np.cos(e2) * np.cos(a1 - a2)
    return np.degrees(np.arccos(np.clip(cosd, -1.0, 1.0)))


def our_edges(target: str, c: Case, t0_et: float, t1: float) -> list[tuple[float, bool]]:
    """Rise (True) and set (False) over the flat horizon: 30 s grid, then bisection."""
    t = np.arange(0.0, t1 + 15.0, 30.0)
    t[-1] = t1

    def el_at(ts: np.ndarray) -> np.ndarray:
        return our_look(target, c, t0_et, ts)[1]

    def refine(lo: float, hi: float) -> float:
        up_lo = bool(el_at(np.array([lo]))[0] > 0.0)
        while hi - lo > 1e-3:
            mid = 0.5 * (lo + hi)
            if bool(el_at(np.array([mid]))[0] > 0.0) == up_lo:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    runs = intervals.runs_from_margin(t, el_at(t), refine=refine)
    return [(r.start, r.value) for r in runs[1:]]


def table_edges(tab: np.ndarray) -> list[tuple[float, bool]]:
    t, el = tab[:, 0], tab[:, 2]
    out = []
    for i in np.flatnonzero((el[1:] > 0.0) != (el[:-1] > 0.0)):
        x = t[i] + (t[i + 1] - t[i]) * (-el[i]) / (el[i + 1] - el[i])
        out.append((float(x), bool(el[i + 1] > 0.0)))
    return out


def run_case(client: httpx.Client, tmp: Path, c: Case, oid: str, naif: int) -> dict[str, Any]:
    t1 = (c.end - c.start).total_seconds()
    t0_et = spice.utc_to_et(c.start.strftime("%Y-%m-%dT%H:%M:%S"))
    vec = vectors(client, naif, c)
    rows = np.asarray(vec["rows"])
    kp = tmp / f"{oid}-{c.start:%Y%m%d}.bsp"
    spice.write_spk13(kp, naif, rows[:, 0], rows[:, 1:], segment=oid)
    spice.load_extra([kp])
    tab = observer_table(client, naif, c, int(round(t1 / 2.0)))
    minute = tab[::30]
    up = minute[:, 2] > 0.0
    az, el = our_look(str(naif), c, t0_et, minute[:, 0])
    sep = separation_deg(az, el, minute[:, 1], minute[:, 2])[up]
    d_el = np.abs(el - minute[:, 2])[up]
    ours = our_edges(str(naif), c, t0_et, t1)
    theirs = table_edges(tab)
    dts = []
    for t_h, rising in theirs:
        cand = [t for t, r in ours if r == rising]
        if cand:
            dts.append(min(abs(t - t_h) for t in cand))
    unmatched = abs(len(ours) - len(theirs))
    spice.unload_extra([kp])
    return {
        "site": c.site,
        "orbiter": oid,
        "start": c.start.isoformat(),
        "end": c.end.isoformat(),
        "horizons_source": vec.get("source"),
        "minutes_up": int(up.sum()),
        "max_sep_deg": float(sep.max()) if sep.size else None,
        "max_d_el_deg": float(d_el.max()) if d_el.size else None,
        "edges": len(theirs),
        "edges_unmatched": unmatched,
        "max_edge_dt_s": float(max(dts)) if dts else None,
    }


def naif_check(client: httpx.Client) -> dict[str, Any]:
    """LRO az/el from NAIF's reconstruction against ours built from Horizons."""
    c = NAIF_LRO
    t1 = (c.end - c.start).total_seconds()
    t0_et = spice.utc_to_et(c.start.strftime("%Y-%m-%dT%H:%M:%S"))
    naif_spk = get_settings().data_dir / "validation" / "lro" / "lrorg_2025074_2025166_v01.bsp"
    ts = np.arange(0.0, t1, 60.0)
    spice.load_extra([naif_spk])
    az_n, el_n = our_look("-85", c, t0_et, ts)
    spice.unload_extra([naif_spk])
    vec = vectors(client, -85, c)
    rows = np.asarray(vec["rows"])
    with tempfile.TemporaryDirectory() as d:
        kp = Path(d) / "lro-naif-check.bsp"
        spice.write_spk13(kp, -85, rows[:, 0], rows[:, 1:], segment="lro")
        spice.load_extra([kp])
        az, el = our_look("-85", c, t0_et, ts)
        spice.unload_extra([kp])
    up = el_n > 0.0
    sep = separation_deg(az, el, az_n, el_n)
    return {
        "site": c.site,
        "start": c.start.isoformat(),
        "end": c.end.isoformat(),
        "kernel": naif_spk.name,
        "minutes_up": int(up.sum()),
        "max_sep_deg_up": float(sep[up].max()) if up.any() else None,
        "max_sep_deg_all": float(sep.max()),
    }


def main() -> int:
    spice.load(get_settings().kernel_dir)
    results = []
    with httpx.Client() as client, tempfile.TemporaryDirectory() as d:
        for c in CASES:
            for oid, naif in ORBITERS:
                try:
                    res = run_case(client, Path(d), c, oid, naif)
                except Exception as exc:
                    res = {"site": c.site, "orbiter": oid, "error": str(exc)[:300]}
                results.append(res)
                print(json.dumps(res), file=sys.stderr)
        naif_res = naif_check(client)
    out = {
        "computed_at": datetime.now(UTC).isoformat(),
        "tolerance": {"az_el_deg": 0.02, "rise_set_s": 2.0, "naif_deg": 0.01},
        "cases": results,
        "naif_lro": naif_res,
    }
    p = get_settings().data_dir / "contact" / "orbiters_check.json"
    p.write_text(json.dumps(out, indent=1) + "\n")
    print("| Site | Orbiter | Minutes up | Max angle (deg) | Max Δel (deg) | Edges | Max Δt (s) |")
    print("|---|---|---:|---:|---:|---:|---:|")
    worst_sep, worst_dt = 0.0, 0.0
    for r in results:
        if "error" in r:
            print(f"| {r['site']} | {r['orbiter']} | error: {r['error'][:60]} | | | | |")
            continue
        s = r["max_sep_deg"]
        dt = r["max_edge_dt_s"]
        worst_sep = max(worst_sep, s or 0.0)
        worst_dt = max(worst_dt, dt or 0.0)
        unmatched = f" ({r['edges_unmatched']} unmatched)" if r["edges_unmatched"] else ""
        print(
            f"| {r['site']} | {r['orbiter']} | {r['minutes_up']} | "
            f"{'-' if s is None else f'{s:.4f}'} | "
            f"{'-' if r['max_d_el_deg'] is None else f'{r['max_d_el_deg']:.4f}'} | "
            f"{r['edges']}{unmatched} | "
            f"{'-' if dt is None else f'{dt:.3f}'} |"
        )
    n = naif_res
    print(
        f"\nNAIF LRO check ({n['kernel']}): max angle {n['max_sep_deg_up']:.5f} deg while up "
        f"({n['minutes_up']} min), {n['max_sep_deg_all']:.5f} deg over all."
    )
    ok = worst_sep <= 0.02 and worst_dt <= 2.0 and (n["max_sep_deg_up"] or 0.0) <= 0.01
    verdict = "PASS" if ok else "FAIL"
    print(f"\nworst angle {worst_sep:.4f} deg, worst edge {worst_dt:.3f} s: {verdict}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
