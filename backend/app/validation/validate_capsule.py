"""Capsule entry against OSIRIS-REx (plan track H).

Run: ``make validate-capsule`` (or ``uv run python -m app.validation.validate_capsule``).
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
  cannot be read by SPICE, so its landing points are taken from their paper.)
  Their simulation (POST2, six degrees of freedom) from the same reconstructed
  entry state, with the parachute sequence as flown and its pre-flight Earth-GRAM
  atmosphere and winds, landed 8.9 km from the measured point ("Cht Seq + ESF");
  with the reconstructed GEOS atmosphere and winds, 3.5 km, beyond it ("Cht Seq +
  ESF + Atm"). The capsule flew without either parachute until 1.4 km above the
  ground (the drogue's release and mortar signals were reversed), so a model
  with no parachutes follows the real flight nearly to the ground.
* **Atmosphere.** The model flies through NRLMSIS 2.1 driven by the entry day's
  solar flux and geomagnetic activity (``data.msis_indices``, from the OMNI files
  on disk); the U.S. Standard Atmosphere 1976 stands in when those are missing.
  Which empirical model is the default is decided by how near each comes to measured air
  between 30 and 70 km (``capsule_air``: TIMED/SABER's profiles of the day and a Rayleigh
  lidar's nights beside it, ``capsule_air_data`` for where they are from), by a rule that
  reads no landing (``capsule_air`` says how it came about, after the first landings were
  known), and this script stops if the default is not the model the measurements pick. All
  of them are flown here over the published drag range,
  so the table says what the atmosphere does to the landing, how far the models' densities
  are from the standard atmosphere along the flight, and what the day's solar flux and
  geomagnetic activity change. Two more tables say what the result rests on: which heights
  decide the landing (the density raised 5 % in one band at a time), and the models'
  densities against the day's own radiosonde.
* **Footprint.** A seeded Monte Carlo from the published delivery accuracy and
  assumed spreads of beta, density and the wind below 30 km, for the 99 % ellipse
  (and again with no wind, to show what sets its width).

The result is written to ``data/capsule/orex_check.json`` (committed), which
``GET /missions/{id}/return`` serves as the capsule model's check.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import numpy as np

from app.config import get_settings
from app.core import atmosphere, entry, spice
from app.data import msis_indices, registry
from app.services import capsule
from app.validation import capsule_air, capsule_air_data

SRC = "-64090"
#: Recovery team's measured landing point (Francis et al., AAS 24).
MEASURED = (40.3719, -113.24)
#: The EDL team's simulation from the reconstructed entry state, with the parachute sequence
#: as flown and its pre-flight atmosphere and winds ("Cht Seq + ESF" in the paper's table of
#: comparison cases): distance from the measured point.
EDL_TEAM_KM = 8.9
#: The same simulation with the reconstructed GEOS atmosphere and winds ("Cht Seq + ESF +
#: Atm"): it lands 3.5 km beyond the measured point.
EDL_TEAM_DAY_KM = 3.5
LIMIT_KM = 10.0
SOURCES = (
    "https://naif.jpl.nasa.gov/pub/naif/pds/pds4/orex/orex_spice/spice_kernels/spk/"
    "src_230924_230924_230930_od383a_v1.bsp",
    "Francis et al., Entry, Descent, and Landing Analysis for the OSIRIS-REx Sample Return "
    "Capsule (AAS 24), https://ntrs.nasa.gov/citations/20240000629",
    "Wibben et al., AAS 24-058, Table 12 (reconstructed entry state)",
    "Mitcheltree et al. 1997 and Wilmoth et al. 1997 (Stardust capsule shape and axial force)",
    "Emmert et al., NRLMSIS 2.1: an empirical model of nitric oxide incorporated into MSIS, "
    "J. Geophys. Res. Space Physics 127, e2022JA030896 (2022) (the air flown, run through "
    "pymsis 0.13.0; NRLMSIS 2.0 with nitric oxide added)",
    "Picone et al., NRLMSISE-00 empirical model of the atmosphere: statistical comparisons and "
    "scientific issues, J. Geophys. Res. 107(A12), 1468 (2002), doi:10.1029/2002JA009430 "
    "(flown for comparison)",
    "NASA SPDF, OMNI hourly data: the 10.7 cm solar flux and the 3-hour ap from NOAA NGDC",
    "National Weather Service radiosonde, Salt Lake City (KSLC, WMO 72572), 24 September 2023 "
    "12 UTC, from the Iowa Environmental Mesonet archive: "
    "https://mesonet.agron.iastate.edu/json/raob.py?ts=202309241200&station=KSLC",
    "TIMED/SABER Level 2A version 2.08 temperature and number density, 24 September 2023 "
    "(GATS, from NASA CDAWeb): " + capsule_air_data.SABER_URL,
    "NASA JPL Table Mountain Facility Rayleigh lidar temperature and density, 19 to 30 "
    "September 2023 (NDACC): " + capsule_air_data.TMF_URL,
    "Emmert et al., NRLMSIS 2.0: A whole-atmosphere empirical model of temperature and "
    "neutral species densities, Earth and Space Science 8, e2020EA001321 (2021), "
    "doi:10.1029/2020EA001321 (Table 1: the data sets it was fitted to; Table 2 and section "
    "6.1: how it compares with NRLMSISE-00)",
    "GATS, SABER Calibration and Measurement Algorithm Document, 22 September 2022, section "
    "5.2.1.1 (how temperature and pressure are retrieved): "
    "https://saber.gats-inc.com/documents/SABER-CMAD-9-22-2022.pdf",
)
OUT = "capsule/orex_check.json"
TOUCHDOWN_M = 1288.0
OBSERVED_S = 615.1  # entry to touchdown (Williams et al., AIAA SciTech 2025, Table 4)
RUNS = 200
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


def _landings(
    et0: float, r0: np.ndarray, v0: np.ndarray, atm: capsule.Atmosphere
) -> list[tuple[float, float, capsule.Landing, float]]:
    """(C_A, beta, landing, kilometres from the measured point) over the drag range."""
    rows = []
    for ca in (CA[0], sum(CA) / 2, CA[1]):
        b = beta(ca)
        ld = capsule.land(et0, r0, v0, entry.Capsule(b, air=atm.air), TOUCHDOWN_M)
        d = capsule.distance_km(ld.lat_deg, ld.lon_deg, *MEASURED)
        print(f"{atm.name} CA {ca}: {ld}", file=sys.stderr)
        rows.append((ca, b, ld, d))
    return rows


def _footprint(
    et0: float,
    r0: np.ndarray,
    v0: np.ndarray,
    atm: capsule.Atmosphere,
    ref: capsule.Landing,
    spread: entry.Spread = SPREAD,
) -> tuple[int, dict[str, float], bool]:
    """(runs, the 99 % ellipse about the middle landing, whether it holds the measured point)."""
    fp = capsule.footprint(
        et0, r0, v0, entry.Capsule(beta(sum(CA) / 2), air=atm.air), spread, TOUCHDOWN_M, RUNS
    )
    en = [capsule.local_km(ref.lat_deg, ref.lon_deg, x.lat_deg, x.lon_deg) for x in fp]
    ell = entry.ellipse_km(np.array([e for e, _ in en]), np.array([n for _, n in en]))
    inside = _inside(ell, *capsule.local_km(ref.lat_deg, ref.lon_deg, *MEASURED))
    return len(fp), ell, inside


def _atmosphere(atm: capsule.Atmosphere) -> dict[str, Any]:
    return {
        "name": atm.name,
        "f107_sfu": None if atm.f107_sfu is None else round(atm.f107_sfu, 1),
        "f107_mean_81_day_sfu": None if atm.f107_mean_sfu is None else round(atm.f107_mean_sfu, 1),
        "ap_3_hour": atm.ap_3h,
        "indices_from": list(atm.files),
        "standard_atmosphere_instead": atm.fallback_reason,
    }


#: Heights (km) where the models' densities are compared along the flight.
COMPARE_KM = (100, 80, 60, 50, 40, 30, 20, 10)


def _density_along(
    et0: float, r0: np.ndarray, v0: np.ndarray, atms: list[capsule.Atmosphere]
) -> None:
    """Each model's density over the standard atmosphere's, at the points of the flight the
    middle drag coefficient makes through the standard atmosphere."""
    pole = capsule.pole_at(et0)
    fl = entry.fly(r0, v0, pole, entry.Capsule(beta(sum(CA) / 2)), TOUCHDOWN_M)
    order = np.argsort(fl.height_m)  # np.interp wants rising heights
    print(
        "\n| Height | Time from entry | " + " | ".join(f"{a.name} / standard" for a in atms) + " |"
    )
    print("|---|---|" + "---|" * len(atms))
    for km in COMPARE_KM:
        h = km * 1000.0
        t = float(np.interp(h, fl.height_m[order], fl.t_s[order]))
        r = np.array([np.interp(t, fl.t_s, fl.r_m[:, k]) for k in range(3)])
        std = atmosphere.density(h)
        cells = [f"{a.air(t, r, h) / std:.3f}" for a in atms if a.air is not None]
        print(f"| {km} km | {t:.0f} s | " + " | ".join(cells) + " |")


def _what_moves_the_landing(
    et0: float, r0: np.ndarray, v0: np.ndarray, used: capsule.Atmosphere
) -> None:
    """The landing of the middle case (km from the measured point) when the density is scaled,
    and when the day's model is given other solar flux and geomagnetic activity."""
    b = beta(sum(CA) / 2)
    print("\n| Change | From the measured point | East, north of the measured point |")
    print("|---|---|---|")

    def row(label: str, cap: entry.Capsule) -> None:
        ld = capsule.land(et0, r0, v0, cap, TOUCHDOWN_M)
        east, north = capsule.local_km(*MEASURED, ld.lat_deg, ld.lon_deg)
        d = capsule.distance_km(ld.lat_deg, ld.lon_deg, *MEASURED)
        print(f"| {label} | {d:.1f} km | {east:+.1f}, {north:+.1f} km |")

    for k in (0.90, 0.95, 1.00, 1.05, 1.10):
        row(f"Standard atmosphere, density x {k:.2f}", entry.Capsule(b, density_scale=k))
    if used.air is None or used.f107_sfu is None or used.ap_3h is None:
        return
    when = capsule.utc(et0)
    rot0 = spice.rotations("J2000", "ITRF93", np.array([et0]))[0]
    ix = msis_indices.at(when)
    assert ix is not None
    for label, f107, f107a, ap in (
        ("the day's flux and ap", ix.f107, ix.f107a, ix.ap),
        ("F10.7 70 sfu (solar minimum)", 70.0, 70.0, ix.ap),
        ("F10.7 250 sfu (solar maximum)", 250.0, 250.0, ix.ap),
        ("quiet field (ap 4 throughout)", ix.f107, ix.f107a, (4.0,) * 7),
        ("a severe storm (ap 100 throughout)", ix.f107, ix.f107a, (100.0,) * 7),
    ):
        air = capsule.msis_air(when, rot0, f107, f107a, ap, capsule.MSIS_VERSIONS[used.name])
        row(f"{used.name}, {label}", entry.Capsule(b, air=air))


#: Height bands (km) of the table of which heights decide the landing.
BANDS_KM = ((0, 30), (30, 50), (50, 70), (70, 90), (90, 125))


def _denser_in(base: entry.Air, lo_km: float, hi_km: float, k: float) -> entry.Air:
    """``base`` with its density multiplied by ``k`` between two heights."""

    def air(t_s: float, r: np.ndarray, h: float) -> float:
        return base(t_s, r, h) * (k if lo_km * 1000.0 <= h < hi_km * 1000.0 else 1.0)

    return air


def _which_heights(et0: float, r0: np.ndarray, v0: np.ndarray, used: capsule.Atmosphere) -> None:
    """Where the middle case lands when the air it flies through is 5 % denser in one band of
    heights at a time: the bands that decide the landing, and so the ones that have to be
    right for the day."""
    b = beta(sum(CA) / 2)
    base = used.air or (lambda _t, _r, h: atmosphere.density(h))
    ref = capsule.land(et0, r0, v0, entry.Capsule(b, air=used.air), TOUCHDOWN_M)
    print(
        f"\n| {used.name}, density 5 % higher between | Landing moves | From the measured point |"
    )
    print("|---|---|---|")
    for lo, hi in BANDS_KM:
        ld = capsule.land(
            et0, r0, v0, entry.Capsule(b, air=_denser_in(base, lo, hi, 1.05)), TOUCHDOWN_M
        )
        moved = capsule.distance_km(ref.lat_deg, ref.lon_deg, ld.lat_deg, ld.lon_deg)
        d = capsule.distance_km(ld.lat_deg, ld.lon_deg, *MEASURED)
        print(f"| {lo} and {hi} km | {moved:.2f} km | {d:.1f} km |")


#: The Salt Lake City radiosonde (KSLC, WMO 72572; 40.77 N, 111.95 W, 1,289 m) of 12 UTC on the
#: entry day, about 130 km from the touchdown, as the Iowa Environmental Mesonet archives the
#: National Weather Service's soundings (saved unchanged; the address is in SOURCES). It reaches
#: 33 km, and its heights are geopotential.
RAOB = "capsule/kslc_20230924_12z.json"
RAOB_AT = (40.77, -111.95)
RAOB_KM = (3, 5, 10, 15, 20, 25, 30)
R_DRY = 287.05  # J/(kg K)


def _radiosonde() -> tuple[datetime, np.ndarray, np.ndarray]:
    """(time, geometric heights in m, rising, air density in kg/m^3) at the radiosonde's levels
    that give a pressure, height and temperature; the dew point, where the balloon gave one,
    makes the temperature virtual."""
    raw = json.loads((get_settings().data_dir / RAOB).read_text())["profiles"][0]
    levels = sorted(
        (lv for lv in raw["profile"] if None not in (lv["pres"], lv["hght"], lv["tmpc"])),
        key=lambda lv: lv["hght"],
    )
    zs: list[float] = []
    rhos: list[float] = []
    for lv in levels:
        z = atmosphere.geometric_m(float(lv["hght"]))
        if zs and z <= zs[-1]:
            continue
        w = 0.0
        if lv["dwpc"] is not None:  # mixing ratio from the dew point (Bolton 1980)
            e = 6.112 * math.exp(17.67 * lv["dwpc"] / (lv["dwpc"] + 243.5))
            w = 0.622 * e / (lv["pres"] - e)
        zs.append(z)
        rhos.append(lv["pres"] * 100.0 / (R_DRY * (lv["tmpc"] + 273.15) * (1.0 + 0.61 * w)))
    when = datetime.fromisoformat(raw["valid"].replace("Z", "+00:00"))
    return when, np.array(zs), np.array(rhos)


def _against_radiosonde() -> dict[str, float]:
    """Each model's density over the radiosonde's, at the heights the balloon reached; the
    largest difference of each from the balloon's, as a fraction."""
    when, z, rho = _radiosonde()
    ix = msis_indices.at(when)
    names = [capsule.STANDARD_NAME] + ([] if ix is None else list(capsule.MSIS_VERSIONS))
    print(
        "\n| Height | Radiosonde (kg/m³) | " + " | ".join(f"{n} / radiosonde" for n in names) + " |"
    )
    print("|---|---|" + "---|" * len(names))
    worst = dict.fromkeys(names, 0.0)
    for km in RAOB_KM:
        h = km * 1000.0
        seen = float(math.exp(np.interp(h, z, np.log(rho))))
        cells = []
        for n in names:
            if ix is None or n == capsule.STANDARD_NAME:
                model = atmosphere.density(h)
            else:
                model = capsule.msis_density(
                    when, *RAOB_AT, h, ix.f107, ix.f107a, ix.ap, capsule.MSIS_VERSIONS[n]
                )
            cells.append(f"{model / seen:.3f}")
            worst[n] = max(worst[n], abs(model / seen - 1.0))
        print(f"| {km} km | {seen:.4g} | " + " | ".join(cells) + " |")
    print(
        f"Balloon of {when:%H} UTC, up to {z[-1] / 1000.0:.0f} km; largest difference from it: "
        + ", ".join(f"{n} {100 * w:.1f} %" for n, w in worst.items())
    )
    return worst


def main() -> None:
    spice.load(get_settings().kernel_dir)
    et0, r0, v0 = _entry()
    got = capsule.entry_state(r0, v0, et0)
    print(f"Entry {spice.et_to_utc(et0)} UTC, radius {got['radius_km']:.3f} km")
    print("\n| Entry state | Published (reconstruct) | From the SPK | Difference |")
    print("|---|---|---|---|")
    for k, v in PUBLISHED.items():
        print(f"| {k} | {v} | {got[k]:.3f} | {got[k] - v:+.3f} |")

    # The air the model flies through, and the others for comparison. The default must be the
    # model the measurements of the air between 30 and 70 km pick (capsule_air).
    evidence = capsule_air.evidence()
    capsule_air.print_tables(evidence)
    if evidence["chosen"] != capsule.DEFAULT_MODEL:
        raise SystemExit(
            f"capsule.DEFAULT_MODEL is {capsule.DEFAULT_MODEL}, but the measured air picks "
            f"{evidence['chosen']}"
        )
    used = capsule.day_atmosphere(et0)
    atmospheres = [capsule.standard()]
    if used.air is not None:
        atmospheres += [
            used if name == used.name else capsule.day_atmosphere(et0, name)
            for name in capsule.MSIS_VERSIONS
        ]
    else:
        atmospheres = [used]
    print(
        f"\nAir for the day: {used.name}, F10.7 {used.f107_sfu} sfu (81-day mean "
        f"{used.f107_mean_sfu}), ap {used.ap_3h} (3 h at the time); "
        f"{used.fallback_reason or 'from ' + ', '.join(used.files)}"
    )
    flown = {a.name: _landings(et0, r0, v0, a) for a in atmospheres}

    print("\n| Atmosphere | C_A 1.48 | C_A 1.52 | C_A 1.56 | Entry to ground | Peak g |")
    print("|---|---|---|---|---|---|")
    for a in atmospheres:
        rows = flown[a.name]
        ld = rows[1][2]
        print(
            f"| {a.name}{' (used)' if a is used else ''} | "
            + " | ".join(f"{r[3]:.1f} km" for r in rows)
            + f" | {ld.duration_s:.0f} s | {ld.peak_g:.1f} |"
        )
    print("\n| C_A | beta (kg/m²) | Landing | From the measured point | Entry to ground | Peak g |")
    print("|---|---|---|---|---|---|")
    for ca, b, ld, d in flown[used.name]:
        print(
            f"| {ca:.2f} | {b:.1f} | {ld.lat_deg:.4f} N, {-ld.lon_deg:.4f} W | {d:.1f} km | "
            f"{ld.duration_s:.0f} s | {ld.peak_g:.1f} |"
        )
    print(f"Observed entry to touchdown: {OBSERVED_S} s")
    if len(atmospheres) > 1:
        _density_along(et0, r0, v0, atmospheres[1:])
    _what_moves_the_landing(et0, r0, v0, used)
    _which_heights(et0, r0, v0, used)
    _against_radiosonde()

    # Footprints: the model as used, and the standard atmosphere it replaced (both cheap enough).
    feet: dict[str, tuple[int, dict[str, float], bool]] = {}
    for a in (atmospheres[0], used):
        if a.name not in feet:
            feet[a.name] = _footprint(et0, r0, v0, a, flown[a.name][1][2])
            n, ell, inside = feet[a.name]
            print(
                f"\nFootprint in {a.name}, {n} runs: 99 % ellipse "
                f"{2 * ell['semi_major_km']:.1f} by {2 * ell['semi_minor_km']:.1f} km, long axis "
                f"{ell['azimuth_deg']:.0f} deg from north; the measured point is "
                f"{'inside' if inside else 'outside'} it."
            )

    # What sets the ellipse's width: the same runs with no wind.
    calm_n, calm, calm_inside = _footprint(
        et0, r0, v0, used, flown[used.name][1][2], replace(SPREAD, wind_m_s=0.0)
    )
    print(
        f"\nFootprint in {used.name} with no wind, {calm_n} runs: 99 % ellipse "
        f"{2 * calm['semi_major_km']:.1f} by {2 * calm['semi_minor_km']:.1f} km; the measured "
        f"point is {'inside' if calm_inside else 'outside'} it."
    )

    mid = flown[used.name][1]
    ds = [r[3] for r in flown[used.name]]
    _, ell, inside = feet[used.name]
    compared = []
    for a in atmospheres:
        rows = flown[a.name]
        e = feet.get(a.name)
        compared.append(
            {
                "name": a.name,
                "used": a is used,
                "distance_km": round(rows[1][3], 1),
                "distance_range_km": [
                    round(min(r[3] for r in rows), 1),
                    round(max(r[3] for r in rows), 1),
                ],
                "ellipse_99_km": None
                if e is None
                else [round(2 * e[1]["semi_major_km"], 1), round(2 * e[1]["semi_minor_km"], 1)],
                "measured_inside_ellipse": None if e is None else e[2],
            }
        )
    check = {
        "case": "OSIRIS-REx sample return capsule, 24 September 2023",
        "entry_utc": spice.et_to_utc(et0),
        "atmosphere": _atmosphere(used),
        "atmosphere_choice": evidence,
        "measured": {"lat_deg": MEASURED[0], "lon_deg": MEASURED[1]},
        "modelled": {"lat_deg": round(mid[2].lat_deg, 4), "lon_deg": round(mid[2].lon_deg, 4)},
        "distance_km": round(mid[3], 1),
        "distance_range_km": [round(min(ds), 1), round(max(ds), 1)],
        "limit_km": LIMIT_KM,
        "passed": mid[3] <= LIMIT_KM,
        "edl_team_km": EDL_TEAM_KM,
        "edl_team_day_km": EDL_TEAM_DAY_KM,
        "atmospheres": compared,
        "beta_kg_m2": round(mid[1], 1),
        "ellipse_99_km": [round(2 * ell["semi_major_km"], 1), round(2 * ell["semi_minor_km"], 1)],
        "measured_inside_ellipse": inside,
        "ellipse_99_no_wind_km": [
            round(2 * calm["semi_major_km"], 1),
            round(2 * calm["semi_minor_km"], 1),
        ],
        "measured_inside_ellipse_no_wind": calm_inside,
        "runs": feet[used.name][0],
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
