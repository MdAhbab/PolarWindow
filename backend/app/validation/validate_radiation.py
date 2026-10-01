"""Radiation screening checks (plan track E).

Run: ``make validate-radiation`` (or ``uv run python -m app.validation.validate_radiation``).
Prints the tables in docs/validation.md.

* **Belts, two implementations**: along each flown trajectory (one-minute samples
  within 15 Earth radii), the fluence of electrons above 1 MeV and protons above
  10 MeV from IRBEM (the engine) and from NASA SPDF's AE8/AP8 code (``radbelt``).
  The separate compare_spenvis runner checks downloaded SPENVIS spectra. This
  runner compares the engine with the other public implementation of
  the same maps, twice: with the same magnetic shells (IRBEM's L and B/B0, from the
  field each map was built with, as SPENVIS lists them), which checks the maps and
  their reading; and with SPDF's own shells (IGRF of the flight date, B0 the field
  line's minimum), which shows how much the choice of field moves the answer.
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
import radbelt

from app.config import get_settings
from app.core import belts, forces, gcr, spice
from app.data import registry, space_climate
from app.services import ascent, lifecycle, radiation

MISSIONS = ("im-1", "im-2", "blue-ghost-m1", "peregrine-m1")
CRATER_MICRO = 18.9
CRATER_D1D2 = 16.5


def _radbelt(
    particle: str, solar: str, energy: float, times: list, geo_km: np.ndarray
) -> np.ndarray:
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
            lm, bb0 = belts.shells(particle, phase.solar, times, geo)  # type: ignore[arg-type]
            ok = np.isfinite(lm)
            c = np.zeros_like(a)
            c[ok] = np.asarray(
                radbelt.aep8(energy, lm[ok], bb0[ok], particle, phase.solar), dtype=float
            )
            fa, fb, fc = (
                sum(belts.fluence(t[s], f[s]) for s in radiation._segments(t)) for f in (a, b, c)
            )
            row[f"{particle}_irbem"] = fa
            row[f"{particle}_same"] = fc
            row[f"{particle}_same_diff"] = (fa - fc) / fc if fc > 0 else None
            row[f"{particle}_radbelt"] = fb
            row[f"{particle}_diff"] = (fa - fb) / fb if fb > 0 else None
        if mid == "im-2":
            row["p_why"] = _why(phase.solar, t, times, geo)
        rows.append(row)
        print(row, file=sys.stderr)
    return rows


def _why(solar: str, t: np.ndarray, times: list, geo: np.ndarray) -> dict[str, float]:
    """Proton fluence >10 MeV read with other shells: the same maps and code (SPDF's),
    only the field (and its date) or B0 changed."""
    e = radiation.P_MEV
    lm, bb0 = belts.shells("p", solar, times, geo)  # type: ignore[arg-type]
    ok = np.isfinite(lm)
    flux = np.zeros(lm.size)
    flux[ok] = np.asarray(radbelt.aep8(e, lm[ok], bb0[ok], "p", solar), dtype=float)
    out = {"GSFC 12/66 with published SAA drift compensation":
           sum(belts.fluence(t[s], flux[s]) for s in radiation._segments(t))}
    for name, field, year, b0_min in (
        ("GSFC 12/66, drift compensation disabled", 3, None, False),
        ("IGRF of 1970", 0, 1970, False),
        ("IGRF of the flight date", 0, None, False),
        ("IGRF of the flight date, B0 the field line's minimum", 0, None, True),
    ):
        lm, bl, bm = belts.field_lines(times, geo, field, year)
        ok = np.isfinite(lm)
        b0 = bm if b0_min else belts.MCILWAIN_M_NT / lm**3
        f = np.zeros(lm.size)
        f[ok] = np.asarray(radbelt.aep8(e, lm[ok], (bl / b0)[ok], "p", solar), dtype=float)
        out[name] = sum(belts.fluence(t[s], f[s]) for s in radiation._segments(t))
    return out


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

    def pct(x: object) -> str:
        return "-" if x is None else f"{100 * float(x):+.1f} %"  # type: ignore[arg-type]

    print("\nSame shells (IRBEM's L and B/B0 into both codes):")
    print(
        "\n| Mission | 1-min samples | Maps | e >1 MeV IRBEM | SPDF | diff "
        "| p >10 MeV IRBEM | SPDF | diff |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if not r.get("samples"):
            print(f"| {r['mission']} | 0 | - | - | - | - | - | - | - |")
            continue
        print(
            f"| {r['mission']} | {r['samples']} | {str(r['maps']).upper()} | {r['e_irbem']:.3g} | "
            f"{r['e_same']:.3g} | {pct(r['e_same_diff'])} | {r['p_irbem']:.3g} | "
            f"{r['p_same']:.3g} | {pct(r['p_same_diff'])} |"
        )
    print("\nSPDF's own shells (IGRF of the flight date, B0 the field line's minimum):")
    print("\n| Mission | e >1 MeV SPDF | IRBEM against it | p >10 MeV SPDF | IRBEM against it |")
    print("|---|---|---|---|---|")
    for r in rows:
        if r.get("samples"):
            print(
                f"| {r['mission']} | {r['e_radbelt']:.3g} | {pct(r['e_diff'])} | "
                f"{r['p_radbelt']:.3g} | {pct(r['p_diff'])} |"
            )
    for r in rows:
        for name, v in (r.get("p_why") or {}).items():  # type: ignore[attr-defined]
            print(f"{r['mission']} p >10 MeV, shells from {name}: {v:.3g}")
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
