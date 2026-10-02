"""Rover-to-lander line of sight on real terrain (plan track T1, F5).

Run: ``make validate-viewshed`` (or ``uv run python -m app.validation.validate_viewshed``).
Prints the docs/validation.md table.

The plan asks for 99 % agreement with GDAL outside the uncertain band;
``validate_viewshed_gdal`` now checks that separately through its public C API.
This runner checks the engine's running maximum of elevation angles against a brute-force
test written separately -- for every rover position, the terrain sampled every
metre along the straight line between the antennas, in heights rather than
angles -- on the selected native terrain around each rover site, with height error
set to zero and compared only where that terrain's stated error
would not make it uncertain.
"""

from __future__ import annotations

import sys

import numpy as np

from app.core import viewshed as vs
from app.core.horizon import R_MOON_M, curvature_drop_m
from app.data.lola import DemTile, make_samplers
from app.data.rover_terrain import terrain_path

SITES = [
    ("IM-2 (Yaoki)", "mission-im-2", -84.7906, 29.1957),
    ("Griffin-1 (FLIP)", "feature-mons-mouton", -84.6, 31.0),
    ("Shackleton rim (native 5 m)", "shackleton-rim", -89.29924, 131.6425),
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
    print("| Site | Post | Radius | Cells | Outside the band | Agree | Share out of sight |")
    print("|---|---:|---:|---:|---:|---:|---|")
    worst = 1.0
    for name, sid, lat, lon in SITES:

        def zero(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            return np.zeros(np.shape(x))

        for radius in (500.0, 2000.0):
            fine = DemTile.load(terrain_path(sid, lat, lon, radius))
            sample, sigma = make_samplers(lat, lon, fine, None)
            b = np.arange(0.0, 360.0, 5.0)
            r = radius * np.arange(1, 21) / 20

            exact = _run(sample, zero, b, r, fine.scale_m)
            noisy = _run(sample, sigma, b, r, fine.scale_m)
            ref = brute(sample, b, r, fine.scale_m)
            keep = noisy.sight != vs.UNCERTAIN
            agree = float(np.mean(exact.sight[keep] == ref[keep])) if keep.any() else None
            if agree is not None:
                worst = min(worst, agree)
            agree_words = f"{100 * agree:.2f} %" if agree is not None else "n/a (all uncertain)"
            lo, hi = vs.ground_share(noisy, noisy.sight) or (float("nan"), float("nan"))
            print(
                f"| {name} | {fine.scale_m:g} m | {radius:.0f} m | "
                f"{b.size * r.size} | {int(keep.sum())} | "
                f"{agree_words} | {100 * lo:.1f} to {100 * hi:.1f} % |"
            )
    ok = worst >= 0.99
    print(f"\nworst agreement {100 * worst:.2f} %: {'PASS' if ok else 'FAIL'} (plan: 99 %)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
