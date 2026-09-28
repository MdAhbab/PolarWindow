"""Capsule entry against OSIRIS-REx (plan track H).

Run: ``make validate-capsule`` (or ``uv run python -m app.tests.golden.validate_capsule``).
Prints the tables in docs/validation.md.

* **Entry state.** The sample return capsule's reconstructed trajectory (NAIF's
  PDS archive, OD 383a) ends at the entry interface, 6,503.142 km from the
  Earth's centre, at 14:41:55.072 UTC on 24 September 2023; its state there is
  checked against the reconstructed entry state the navigation team published
  (Wibben et al., AAS 24-058, Table 12).
* **Landing.** From that state the 3-DOF ballistic model, with a ballistic
  coefficient worked out from published numbers, is flown to the touchdown
  height (1,288 m) and its landing point compared with the one the recovery
  team measured, 40.3719 N, 113.24 W (Francis et al., AAS 24, "Entry, Descent,
  and Landing Analysis for the OSIRIS-REx Sample Return Capsule"). The plan asks
  for 10 km. (The EDL team's own simulation from the same state is archived as
  ``src_230924_230924_231027_edlp_v1.bsp``, but its segments after 14:49:14 UTC
  cannot be read by SPICE, so its landing point is taken from their paper.)
  The EDL team's own simulation from the same reconstructed entry state, with
  their pre-flight atmosphere and winds, landed 8.9 km from it (their Table,
  "Cht Seq + ESF"); with the day's reconstructed atmosphere, 3.5 km.
* **Footprint.** A seeded Monte Carlo from the published delivery accuracy and
  assumed spreads of beta, density and the wind below 30 km, for the 99 % ellipse.

The result is written to ``data/capsule/orex_check.json`` (committed), which
``GET /missions/{id}/return`` serves as the capsule model's check.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime

import numpy as np

from app.config import get_settings
from app.core import entry, spice
from app.data import registry
from app.services import capsule

SRC = "-64090"
#: Recovery team's measured landing point (Francis et al., AAS 24).
MEASURED = (40.3719, -113.24)
#: The EDL team's simulation from the reconstructed entry state with pre-flight
#: atmosphere and winds ("Cht Seq + ESF"): distance from the measured point.
EDL_TEAM_KM = 8.9
LIMIT_KM = 10.0
SOURCES = (
    "https://naif.jpl.nasa.gov/pub/naif/pds/pds4/orex/orex_spice/spice_kernels/spk/"
    "src_230924_230924_230930_od383a_v1.bsp",
    "Francis et al., Entry, Descent, and Landing Analysis for the OSIRIS-REx Sample Return "
    "Capsule (AAS 24)",
    "Wibben et al., AAS 24-058, Table 12 (reconstructed entry state)",
    "Mitcheltree et al. 1997 and Wilmoth et al. 1997 (Stardust capsule shape and axial force)",
)
OUT = "capsule/orex_check.json"
TOUCHDOWN_M = 1288.0
OBSERVED_S = 615.1  # entry to touchdown (Williams et al., AIAA SciTech 2025, Table 4)
#: AAS 24-058 Table 12, "Reconstruct".
PUBLISHED = {
    "fpa_j2000_deg": -8.184,
    "lat_geocentric_deg": 37.339,
    "lon_deg": 237.216,
    "speed_ecef_km_s": 12.361,
    "heading_j2000_deg": 66.396,
}
#: Beta from published numbers: the SRC's mass at entry (49.64 kg empty plus the 121.6 g
#: sample; Francis et al.), Stardust's outer mold line (the same forebody and diameter,
#: 0.8128 m; Wilmoth et al. 1997) and its hypersonic axial force coefficient, 1.48-1.56
#: (Mitcheltree et al. 1997).
MASS_KG = 49.64 + 0.1216
DIAMETER_M = 0.8128
CA = (1.48, 1.56)
#: One sigma: flight path angle from TCM-12's 3-sigma delivery (AAS 24-058 Table 5),
#: heading and speed from the E-1 day solution (Table 12); beta from the published C_A
#: range taken as one sigma (±2.6 %); the density's 5 % and the wind's 10 m/s are assumed.
SPREAD = entry.Spread(
    fpa_deg=0.073 / 3, heading_deg=3.18e-3, speed_frac=4.88e-6 / 12.361, beta_frac=0.026,
    density_frac=0.05, wind_m_s=10.0,
)  # fmt: skip


def beta(ca: float) -> float:
    return MASS_KG / (ca * math.pi * (DIAMETER_M / 2) ** 2)


def _entry() -> tuple[float, np.ndarray, np.ndarray]:
    spk = get_settings().data_dir / registry.by_id("naif:orex-src-entry").dest
    spice.load_extra([spk])
    cov = spice.coverage(spk, int(SRC))
    et = cov[-1][1]
    st = spice.states(SRC, "EARTH", "J2000", "NONE", np.array([et]))[0]
    return et, st[:3], st[3:]


def main() -> None:
    spice.load(get_settings().kernel_dir)
    et0, r0, v0 = _entry()
    got = capsule.entry_state(r0, v0, et0)
    print(f"Entry {spice.et_to_utc(et0)} UTC, radius {got['radius_km']:.3f} km")
    print("\n| Entry state | Published (reconstruct) | From the SPK | Difference |")
    print("|---|---|---|---|")
    for k, v in PUBLISHED.items():
        print(f"| {k} | {v} | {got[k]:.3f} | {got[k] - v:+.3f} |")
    rows = []
    for ca in (CA[0], sum(CA) / 2, CA[1]):
        b = beta(ca)
        ld = capsule.land(et0, r0, v0, entry.Capsule(b), TOUCHDOWN_M)
        d = capsule.distance_km(ld.lat_deg, ld.lon_deg, *MEASURED)
        rows.append((ca, b, ld, d))
        print(f"CA {ca}: {ld}", file=sys.stderr)
    print("\n| C_A | beta (kg/m²) | Landing | From the measured point | Entry to ground | Peak g |")
    print("|---|---|---|---|---|---|")
    for ca, b, ld, d in rows:
        print(
            f"| {ca:.2f} | {b:.1f} | {ld.lat_deg:.4f} N, {-ld.lon_deg:.4f} W | {d:.1f} km | "
            f"{ld.duration_s:.0f} s | {ld.peak_g:.1f} |"
        )
    print(f"Observed entry to touchdown: {OBSERVED_S} s")
    b = beta(sum(CA) / 2)
    fp = capsule.footprint(et0, r0, v0, entry.Capsule(b), SPREAD, TOUCHDOWN_M, runs=200)
    ref = rows[1][2]
    en = [capsule.local_km(ref.lat_deg, ref.lon_deg, x.lat_deg, x.lon_deg) for x in fp]
    ell = entry.ellipse_km(np.array([e for e, _ in en]), np.array([n for _, n in en]))
    inside = _inside(ell, *capsule.local_km(ref.lat_deg, ref.lon_deg, *MEASURED))
    print(
        f"\nFootprint, {len(fp)} runs: 99 % ellipse {2 * ell['semi_major_km']:.1f} by "
        f"{2 * ell['semi_minor_km']:.1f} km, long axis {ell['azimuth_deg']:.0f} deg from north; "
        f"the measured point is {'inside' if inside else 'outside'} it."
    )
    mid = rows[1]
    ds = [r[3] for r in rows]
    check = {
        "case": "OSIRIS-REx sample return capsule, 24 September 2023",
        "entry_utc": spice.et_to_utc(et0),
        "measured": {"lat_deg": MEASURED[0], "lon_deg": MEASURED[1]},
        "modelled": {"lat_deg": round(mid[2].lat_deg, 4), "lon_deg": round(mid[2].lon_deg, 4)},
        "distance_km": round(mid[3], 1),
        "distance_range_km": [round(min(ds), 1), round(max(ds), 1)],
        "limit_km": LIMIT_KM,
        "passed": mid[3] <= LIMIT_KM,
        "edl_team_km": EDL_TEAM_KM,
        "beta_kg_m2": round(mid[1], 1),
        "ellipse_99_km": [round(2 * ell["semi_major_km"], 1), round(2 * ell["semi_minor_km"], 1)],
        "measured_inside_ellipse": inside,
        "runs": len(fp),
        "sources": list(SOURCES),
        "checked_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    out = get_settings().data_dir / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(check, indent=2) + "\n")
    print(f"Wrote {out}", file=sys.stderr)


def _inside(ell: dict[str, float], east: float, north: float) -> bool:
    a = math.radians(ell["azimuth_deg"])
    de, dn = east - ell["east_km"], north - ell["north_km"]
    along = de * math.sin(a) + dn * math.cos(a)
    across = de * math.cos(a) - dn * math.sin(a)
    minor = max(ell["semi_minor_km"], 1e-9)
    return (along / ell["semi_major_km"]) ** 2 + (across / minor) ** 2 <= 1


if __name__ == "__main__":
    main()
