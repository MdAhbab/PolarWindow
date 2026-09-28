"""Rover-to-lander line of sight on real terrain (plan track T1, F5).

Run: ``make validate-viewshed`` (or ``uv run python -m app.tests.golden.validate_viewshed``).
Prints the docs/validation.md table.

The plan asks for 99 % agreement with ``gdal_viewshed`` outside the uncertain
band. GDAL is not installed here, so this is the nearest check that can be
run: the engine's running maximum of elevation angles against a brute-force
test written separately -- for every rover position, the terrain sampled every
metre along the straight line between the antennas, in heights rather than
angles -- on the 20 m polar model around each rover site, with the height error
set to zero (so every cell has a state) and compared only where the 2 m error
would not make it uncertain.
"""

from __future__ import annotations

import sys

import numpy as np

from app.config import get_settings
from app.core import viewshed as vs
from app.core.horizon import R_MOON_M, curvature_drop_m
from app.data.lola import DemTile, make_samplers

SITES = [
    ("IM-2 (Yaoki)", "mission-im-2", -84.7906, 29.1957),
    ("Griffin-1 (FLIP)", "feature-mons-mouton", -84.6, 31.0),
]
LANDER, ROVER = 2.0, 0.5


def brute(sample, bearings: np.ndarray, ranges: np.ndarray, post: float) -> np.ndarray:
    h0 = float(sample(np.zeros(1), np.zeros(1))[0])
    eye = h0 + LANDER
    near = 2.0 * post
    out = np.empty((bearings.size, ranges.size), dtype=np.int8)
    for i, b in enumerate(np.radians(bearings)):
        for k, d in enumerate(ranges):
            s = np.arange(near, d - near, 1.0)
            tip = float(sample(np.array([np.sin(b) * d]), np.array([np.cos(b) * d]))[0])
            tip = tip - float(curvature_drop_m(np.array([d]), R_MOON_M)[0]) + ROVER
            if s.size == 0:
                out[i, k] = vs.CLEAR
                continue
            z = sample(np.sin(b) * s, np.cos(b) * s) - curvature_drop_m(s, R_MOON_M)
            line = eye + (tip - eye) * s / d
            out[i, k] = vs.CLEAR if bool(np.all(z < line)) else vs.BLOCKED
    return out


def _run(sample, sig, b: np.ndarray, r: np.ndarray, post: float) -> vs.Viewshed:
    return vs.compute(
        sample,
        sig,
        bearings_deg=b,
        ranges_m=r,
        lander_antenna_m=LANDER,
        rover_antenna_m=ROVER,
        frequency_hz=2.4e9,
        post_m=post,
        step_m=1.0,
    )


def main() -> int:
    s = get_settings()
    print("| Site | Radius | Cells | Outside the band | Agree | Share out of sight |")
    print("|---|---:|---:|---:|---:|---|")
    worst = 1.0
    for name, sid, lat, lon in SITES:
        fine = DemTile.load(s.fine_dem_path(sid))
        sample, sigma = make_samplers(lat, lon, fine, None)

        def zero(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            return np.zeros(np.shape(x))

        for radius in (500.0, 2000.0):
            b = np.arange(0.0, 360.0, 5.0)
            r = radius * np.arange(1, 21) / 20

            exact = _run(sample, zero, b, r, fine.scale_m)
            noisy = _run(sample, sigma, b, r, fine.scale_m)
            ref = brute(sample, b, r, fine.scale_m)
            keep = noisy.sight != vs.UNCERTAIN
            agree = float(np.mean(exact.sight[keep] == ref[keep])) if keep.any() else 1.0
            worst = min(worst, agree)
            lo, hi = vs.ground_share(noisy, noisy.sight) or (float("nan"), float("nan"))
            print(
                f"| {name} | {radius:.0f} m | {b.size * r.size} | {int(keep.sum())} | "
                f"{100 * agree:.2f} % | {100 * lo:.1f} to {100 * hi:.1f} % |"
            )
    ok = worst >= 0.99
    print(f"\nworst agreement {100 * worst:.2f} %: {'PASS' if ok else 'FAIL'} (plan: 99 %)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
