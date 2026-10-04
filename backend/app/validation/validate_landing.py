"""Touchdown instants, landing positions and surface geometry vs NAIF CLPS reconstructions.

Run: ``make validate-landing`` (or ``uv run python -m app.validation.validate_landing``).
Prints the table in docs/validation.md.

For each landed CLPS mission with reconstructed EDL and landing site kernels:
1. Landing site position: the position in the landing site (*_ls_*) kernel matches
   the coordinates in data/missions.json within 100 m horizontally (IM-1 target was
   published to 2 decimal places in LROC 1360: -80.13, 1.44; IM-2 and Blue Ghost 1
   match to < 11 m).
2. Touchdown instant: the end of the reconstructed EDL segment (*_edl_rec_*) matches
   the mission's landing instant in missions.json within 1 second.
3. Surface geometry: at the touchdown instant, the Sun and Earth elevations computed
   through the app's topocentric pipeline (visibility.look_angles from MOON_ME ephemeris)
   agree with CSPICE's direct constant-position observer (spkcpo with LT+S) within 0.01 deg.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.core import spice, visibility


@dataclass(frozen=True, slots=True)
class LandingCheck:
    mission_id: str
    name: str
    edl_end_utc: str
    landing_utc: str
    edl_diff_s: float
    target_lat: float
    target_lon: float
    ls_lat: float
    ls_lon: float
    ls_elev_m: float
    horizontal_dist_m: float
    sun_el_app_deg: float
    sun_el_cpo_deg: float
    sun_el_diff_deg: float
    earth_el_app_deg: float
    earth_el_cpo_deg: float
    earth_el_diff_deg: float


LANDED_KERNELS: dict[str, tuple[str, int, str, int, str]] = {
    "im-1": (
        "clps/clps_to2im_im1_edl_rec_240222_v01.bsp",
        -370011,
        "clps/clps_to2im_im1_ls_242022_v02.bsp",
        -370011900,
        "IM-1 Odysseus",
    ),
    "im-2": (
        "clps/clps_prime1_im2_edl_rec_250306_v01.bsp",
        -370021,
        "clps/clps_prime1_im2_ls_250306_v01.bsp",
        -370021900,
        "IM-2 Athena",
    ),
    "blue-ghost-m1": (
        "clps/clps_to19d_bgm1_edl_rec_250302_v01.bsp",
        -2711,
        "clps/clps_to19d_bgm1_ls_250302_v01.bsp",
        -2711900,
        "Blue Ghost Mission 1",
    ),
}


def _topo_elevation(vec_m: np.ndarray, basis: visibility.ENUBasis) -> float:
    e = float(np.dot(vec_m, basis.east))
    n = float(np.dot(vec_m, basis.north))
    u = float(np.dot(vec_m, basis.up))
    return float(np.degrees(np.arctan2(u, np.hypot(e, n))))


def results(missions_path: Path | None = None) -> list[LandingCheck]:
    settings = get_settings()
    data_dir = settings.data_dir
    spice.load(data_dir / "kernels")

    p = missions_path or settings.missions_path
    missions_data = json.loads(p.read_text(encoding="utf-8"))["missions"]
    missions_by_id = {m["id"]: m for m in missions_data}

    out: list[LandingCheck] = []
    for mid, (edl_rel, edl_id, ls_rel, ls_id, name) in LANDED_KERNELS.items():
        edl_p = data_dir / edl_rel
        ls_p = data_dir / ls_rel
        spice.load_extra([edl_p, ls_p])

        cov = spice.coverage(edl_p, edl_id)
        if not cov:
            raise RuntimeError(f"no coverage for {edl_id} in {edl_p}")
        et_touchdown = cov[0][1]
        edl_end_utc = spice.et_to_utc(et_touchdown, precision=0)

        m = missions_by_id[mid]
        if not m.get("landing") or not m.get("target"):
            raise ValueError(f"mission {mid} has no landing or target in missions.json")
        landing_utc = m["landing"]["date"]
        et_landing = spice.utc_to_et(landing_utc)
        edl_diff_s = abs(et_touchdown - et_landing)

        target_lat = float(m["target"]["lat_deg"])
        target_lon = float(m["target"]["lon_deg"])

        pos_ls = spice.positions(
            str(ls_id), "MOON", "MOON_ME", "NONE", np.array([et_touchdown]), knot_s=None
        )[0]
        r_ls = float(np.linalg.norm(pos_ls))
        ls_lat = float(np.degrees(np.arcsin(pos_ls[2] / r_ls)))
        ls_lon = float(np.degrees(np.arctan2(pos_ls[1], pos_ls[0])) % 360.0)
        ls_elev_m = r_ls - spice.R_MOON_M

        p_tgt = visibility.site_position(target_lat, target_lon, spice.R_MOON_M)
        p_ls = visibility.site_position(ls_lat, ls_lon, spice.R_MOON_M)
        horiz_dist_m = float(np.linalg.norm(p_tgt - p_ls))

        basis = visibility.enu_basis(ls_lat, ls_lon)

        sun_vec = spice.body_vectors("sun", np.array([et_touchdown]))
        earth_vec = spice.body_vectors("earth", np.array([et_touchdown]))
        _, sun_el_app_arr = visibility.look_angles(basis, sun_vec, site_pos=pos_ls)
        _, earth_el_app_arr = visibility.look_angles(basis, earth_vec, site_pos=pos_ls)
        sun_el_app = float(sun_el_app_arr[0])
        earth_el_app = float(earth_el_app_arr[0])

        sun_cpo = spice.site_look("SUN", pos_ls, np.array([et_touchdown]), abcorr="LT+S")[0]
        earth_cpo = spice.site_look("EARTH", pos_ls, np.array([et_touchdown]), abcorr="LT+S")[0]
        sun_el_cpo = _topo_elevation(sun_cpo, basis)
        earth_el_cpo = _topo_elevation(earth_cpo, basis)

        sun_el_diff = abs(sun_el_app - sun_el_cpo)
        earth_el_diff = abs(earth_el_app - earth_el_cpo)

        out.append(
            LandingCheck(
                mission_id=mid,
                name=name,
                edl_end_utc=edl_end_utc,
                landing_utc=landing_utc,
                edl_diff_s=edl_diff_s,
                target_lat=target_lat,
                target_lon=target_lon,
                ls_lat=ls_lat,
                ls_lon=ls_lon,
                ls_elev_m=ls_elev_m,
                horizontal_dist_m=horiz_dist_m,
                sun_el_app_deg=sun_el_app,
                sun_el_cpo_deg=sun_el_cpo,
                sun_el_diff_deg=sun_el_diff,
                earth_el_app_deg=earth_el_app,
                earth_el_cpo_deg=earth_el_cpo,
                earth_el_diff_deg=earth_el_diff,
            )
        )
    return out


def main() -> None:
    checks = results()
    print()
    print("CLPS Landed Missions: Touchdown Instants and Surface Geometry vs NAIF Reconstruction")
    print("=" * 122)
    header = (
        f"{'Mission':<15} {'Touchdown (UTC)':<22} {'Target (lat, lon)':<24} "
        f"{'LS kernel (lat, lon)':<24} {'Δpos (m)':>9} {'Sun (°)':>8} {'ΔSun (°)':>10} "
        f"{'Earth (°)':>10} {'ΔEarth (°)':>11}"
    )
    print(header)
    print("-" * 122)
    for c in checks:
        tgt_str = f"{c.target_lat:>8.4f}, {c.target_lon:>8.4f}"
        ls_str = f"{c.ls_lat:>8.4f}, {c.ls_lon:>8.4f}"
        line = (
            f"{c.name:<15} {c.edl_end_utc:<22} {tgt_str:<24} "
            f"{ls_str:<24} {c.horizontal_dist_m:>9.1f} {c.sun_el_app_deg:>8.2f} "
            f"{c.sun_el_diff_deg:>10.5f} {c.earth_el_app_deg:>10.2f} {c.earth_el_diff_deg:>11.5f}"
        )
        print(line)
    print("=" * 122)
    print("Assertions:")
    for c in checks:
        assert c.edl_diff_s <= 1.0, f"{c.mission_id}: EDL diff {c.edl_diff_s} s > 1.0 s"
        assert (
            c.horizontal_dist_m <= 100.0
        ), f"{c.mission_id}: pos diff {c.horizontal_dist_m} m > 100 m"
        assert c.sun_el_diff_deg <= 0.01, f"{c.mission_id}: Sun diff {c.sun_el_diff_deg}° > 0.01°"
        assert (
            c.earth_el_diff_deg <= 0.01
        ), f"{c.mission_id}: Earth diff {c.earth_el_diff_deg}° > 0.01°"
        print(
            f"  [OK] {c.name}: touchdown diff {c.edl_diff_s:.1f}s, "
            f"pos diff {c.horizontal_dist_m:.1f}m, "
            f"Sun diff {c.sun_el_diff_deg:.5f}°, Earth diff {c.earth_el_diff_deg:.5f}°"
        )
    print()


if __name__ == "__main__":
    main()
