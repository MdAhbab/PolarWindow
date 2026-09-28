"""Radiation screening checks (plan track E).

Run: ``make validate-radiation`` (or ``uv run python -m app.tests.golden.validate_radiation``).
Prints the tables in docs/validation.md.

* **Belts, two implementations**: along each flown trajectory (one-minute samples
  within 15 Earth radii), the fluence of electrons above 1 MeV and protons above
  10 MeV from IRBEM (the engine; its own magnetic shells from IGRF) and from NASA
  SPDF's AE8/AP8 code (``radbelt``: its own shells from its IGRF). The plan asks
  for the engine within 5% of SPENVIS; SPENVIS is a web service and was not run,
  so this compares the engine with the other public implementation of the same
  maps.
* **Cosmic rays, absolute**: the model's dose in thin silicon in free space in
  June 2009 (W from the Oulu monitor) against CRaTER's measured 18.9 cGy a year
  (microdosimeter) and 16.5 (D1-D2) at 10,000 km from the Moon. The plan's
  margin is ±30%.
* **Past events**: the >10 MeV peak integrated from the GOES files against
  NOAA SWPC's list of solar proton events (plan: within 10%).
"""

from __future__ import annotations

import sys

import numpy as np

from app.config import get_settings
from app.core import belts, forces, gcr, spice
from app.data import registry, space_climate
from app.services import ascent, lifecycle, radiation

MISSIONS = ("im-1", "im-2", "blue-ghost-m1", "peregrine-m1")
TOL_BELTS = 0.05
CRATER_MICRO = 18.9
CRATER_D1D2 = 16.5


def _radbelt(
    particle: str, solar: str, energy: float, times: list, geo_km: np.ndarray
) -> np.ndarray:
    import radbelt

    lat, lon, h = zip(*(forces.geodetic(x * 1000.0) for x in geo_km), strict=True)
    year = np.array([t.year + (t.timetuple().tm_yday - 0.5) / 365.25 for t in times])
    lvalue, bb0 = radbelt.igrf(np.array(lon), np.array(lat), np.array(h) / 1000.0, year)
    return np.asarray(radbelt.aep8(energy, lvalue, bb0, particle, solar), dtype=float)


def belts_table() -> list[dict[str, object]]:
    spice.load(get_settings().kernel_dir)
    rows = []
    for mid in MISSIONS:
        ds_id, naif = ascent.RECONSTRUCTED[mid]
        spk = get_settings().data_dir / registry.by_id(ds_id).dest
        spice.load_extra([spk])
        cover = spice.coverage(spk, naif)
        start = lifecycle.parse_time(spice.et_to_utc(cover[0][0]))
        phase = radiation.solar_phase(start)
        assert phase is not None
        t, times, geo = radiation.belt_samples(str(naif), cover)
        if t.size == 0:
            rows.append({"mission": mid, "samples": 0})
            continue
        row: dict[str, object] = {"mission": mid, "samples": int(t.size), "maps": phase.solar}
        for particle, energy in (("e", radiation.E_MEV), ("p", radiation.P_MEV)):
            a = belts.integral_flux(particle, phase.solar, [energy], times, geo)[0]  # type: ignore[arg-type]
            b = _radbelt(particle, phase.solar, energy, times, geo)
            fa = sum(belts.fluence(t[s], a[s]) for s in radiation._segments(t))
            fb = sum(belts.fluence(t[s], b[s]) for s in radiation._segments(t))
            row[f"{particle}_irbem"] = fa
            row[f"{particle}_radbelt"] = fb
            row[f"{particle}_diff"] = (fa - fb) / fb if fb > 0 else None
        rows.append(row)
        print(row, file=sys.stderr)
    return rows


def gcr_check() -> dict[str, float]:
    got = space_climate.oulu_at(lifecycle.parse_time("2009-06-20T00:00:00Z"))
    assert got is not None
    w = max(gcr.W_MIN, gcr.w_from_oulu(got[0]))
    model = gcr.thin_si_dose_gy_s(w) * 365.25 * 86400.0 * 100.0
    return {
        "w": w,
        "model_cgy_yr": model,
        "vs_micro": model / CRATER_MICRO - 1.0,
        "vs_d1d2": model / CRATER_D1D2 - 1.0,
    }


def sep_check() -> list[dict[str, object]]:
    out = []
    for e in space_climate.sep_scenarios():
        if e.get("peak_gt10_pfu") is None:
            continue
        pk = float(e["peak_gt10_pfu"])  # type: ignore[arg-type]
        ref = float(e["swpc_list_peak_pfu"])  # type: ignore[arg-type]
        out.append(
            {
                "event": e["name"],
                "goes_peak": pk,
                "goes_at": e["peak_at"],
                "swpc_peak": ref,
                "swpc_at": e["swpc_list_peak_at"],
                "diff": pk / ref - 1.0,
                "f10": e["fluence_gt10_cm2"],
            }
        )
    return out


def main() -> None:
    rows = belts_table()
    print(
        "\n| Mission | 1-min samples | Maps | e >1 MeV IRBEM | radbelt | diff "
        "| p >10 MeV IRBEM | radbelt | diff |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if not r.get("samples"):
            print(f"| {r['mission']} | 0 | - | - | - | - | - | - | - |")
            continue

        def pct(x: object) -> str:
            return "-" if x is None else f"{100 * float(x):+.1f} %"  # type: ignore[arg-type]

        print(
            f"| {r['mission']} | {r['samples']} | {str(r['maps']).upper()} | {r['e_irbem']:.3g} | "
            f"{r['e_radbelt']:.3g} | {pct(r['e_diff'])} | {r['p_irbem']:.3g} | "
            f"{r['p_radbelt']:.3g} | {pct(r['p_diff'])} |"
        )
    g = gcr_check()
    print(
        f"\nGCR thin silicon, June 2009 (W = {g['w']:.1f}): model {g['model_cgy_yr']:.1f} cGy/yr; "
        f"CRaTER microdosimeter {CRATER_MICRO} ({100 * g['vs_micro']:+.0f} %), D1-D2 "
        f"{CRATER_D1D2} ({100 * g['vs_d1d2']:+.0f} %)"
    )
    print("\n| Event | GOES peak >10 MeV (pfu) | at | SWPC list | at | diff | fluence >10 MeV |")
    print("|---|---|---|---|---|---|---|")
    for s in sep_check():
        print(
            f"| {s['event']} | {s['goes_peak']:,.0f} | {s['goes_at']} | {s['swpc_peak']:,.0f} | "
            f"{s['swpc_at']} | {100 * float(s['diff']):+.1f} % | {float(s['f10']):.3g} |"  # type: ignore[arg-type]
        )


if __name__ == "__main__":
    main()
