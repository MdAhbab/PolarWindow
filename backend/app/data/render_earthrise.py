"""Render the front page's Earthrise: the view from Connecting Ridge toward Earth.

The light theme opens on the Moon's surface with Earth just over the horizon.
That surface is not drawn for the picture: it is the LOLA heights around
Connecting Ridge (candidate site B, high and unusually open, in contact with
Earth about 60% of the time), sampled in a fan in front of a viewer standing
2 m above the ground and looking toward Earth, with the Moon's curvature taken
off each sample so the horizon falls where it falls. Each sample is read from
the heights averaged to its own spacing, so far terrain does not alias. Each
sample also carries whether a low Sun reaches it, worked out by marching
toward the Sun over the same heights, so the shadows are the terrain's own.

Earth is drawn at the elevation it stands at from the site on average (its
direction is the sub-Earth point, 0 deg N 0 deg E; libration moves it by a few
degrees, which the page does not claim to show). The Sun is placed for the
picture: from the right and a little ahead, so the ground falling away toward
Earth is lit and Earth is half lit, as in the Apollo photographs; and ten
degrees up, which is higher than it ever stands at this site (it stays within
about two degrees of the horizon there). At its true height nearly everything
in view is in shadow, and the picture would be of the dark; at ten degrees a
crater shows its bowl, lit on one wall and shaded on the other.

Output (little-endian), read by ``frontend/src/landing/earthrise.ts``:

* header, 8 x float32: azimuth columns, range rows, nearest and farthest range
  (km), half the fan's width (deg), Earth's elevation (deg), the Sun's azimuth
  from the view's centre (deg, + to the right, - to the left) and elevation (deg);
* heights, rows x columns int16, above the viewer's eye (negative below), the
  curvature already taken off, in steps that grow with the range ``r``:
  ``0.005 m + r * 1.25e-4`` (half a centimetre at the viewer's feet, where a
  coarser step would terrace the gentle ground and the low Sun would shade
  every terrace; 20 m at 160 km, well under a pixel);
* light, rows x columns uint8, 0 in the terrain's shadow to 255 in sunlight.

Run: ``uv run python -m app.data.render_earthrise`` (writes the frontend asset).
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import numpy.typing as npt

from app.config import get_settings
from app.core.projections import R_MOON_M, geographic_to_polar, polar_to_geographic
from app.data.lola import DemTile

SITE_LAT = -89.43804
SITE_LON = 222.71699
EYE_M = 2.0
N_AZ = 241
N_R = 360
R0_KM = 0.015
R1_KM = 160.0
HALF_DEG = 45.0
SUN_REL_AZ_DEG = 75.0
SUN_EL_DEG = 10.0
#: The height step: ``STEP_M + range_m * STEP_PER_M`` (see the module docstring).
STEP_M = 0.005
STEP_PER_M = 1.25e-4

OUT = (
    Path(__file__).resolve().parents[3] / "frontend" / "src" / "assets" / "space" / "earthrise.bin"
)

Floats = npt.NDArray[np.float64]


def _unit(lat_deg: float, lon_deg: float) -> Floats:
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    return np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])


def earth_direction_in_grid(x0: float, y0: float) -> tuple[Floats, float]:
    """The grid direction from the site toward Earth, and Earth's elevation there (deg)."""
    s = _unit(SITE_LAT, SITE_LON)
    e = _unit(0.0, 0.0)
    elevation = math.degrees(math.asin(float(np.dot(e, s))))
    t = e - np.dot(e, s) * s
    t /= np.linalg.norm(t)
    d = 1_000.0 / R_MOON_M  # one kilometre along the great circle toward Earth
    p = s * math.cos(d) + t * math.sin(d)
    lat = math.degrees(math.asin(p[2]))
    lon = math.degrees(math.atan2(p[1], p[0]))
    x1, y1 = geographic_to_polar(np.array([lon]), np.array([lat]))
    v = np.array([float(x1[0]) - x0, float(y1[0]) - y0])
    return v / np.linalg.norm(v), elevation


def pyramid(dem: DemTile, levels: int = 5) -> list[DemTile]:
    """The heights averaged 1, 2, 4 ... times over, each a tile in the same grid."""
    out = [dem]
    for _ in range(levels - 1):
        t = out[-1]
        h, w = t.heights.shape
        z = (
            t.heights[: h - h % 2, : w - w % 2]
            .reshape(h // 2, 2, w // 2, 2)
            .mean(axis=(1, 3))
            .astype(np.float32)
        )
        # The averaged post sits at the centre of the four it replaces.
        out.append(
            DemTile(
                heights=z,
                origin_x_m=t.origin_x_m + t.scale_m / 2,
                origin_y_m=t.origin_y_m - t.scale_m / 2,
                scale_m=t.scale_m * 2,
                product=t.product,
                vertical_error_m=t.vertical_error_m,
            )
        )
    return out


def sample(levels: list[DemTile], x: Floats, y: Floats, spacing_m: Floats) -> Floats:
    """Heights at (x, y), each from the level whose post spacing matches its sample spacing."""
    pick = np.clip(
        np.floor(np.log2(np.maximum(spacing_m, 1.0) / levels[0].scale_m)), 0, len(levels) - 1
    ).astype(int)
    out = np.full(x.shape, np.nan)
    for i, t in enumerate(levels):
        m = pick == i
        if m.any():
            out[m] = t.sample_grid(x[m], y[m])
    return out


def render(out: Path = OUT) -> None:
    dem = DemTile.load(get_settings().dem_dir / "regional_80m.npz")
    levels = pyramid(dem)
    xs, ys = geographic_to_polar(np.array([SITE_LON]), np.array([SITE_LAT]))
    x0, y0 = float(xs[0]), float(ys[0])
    fwd, earth_el = earth_direction_in_grid(x0, y0)
    right = np.array([fwd[1], -fwd[0]])  # grid x to the right of the view
    h_site = float(dem.sample_grid(np.array([x0]), np.array([y0]))[0])

    az = np.radians(np.linspace(-HALF_DEG, HALF_DEG, N_AZ))
    r_km = R0_KM * (R1_KM / R0_KM) ** (np.arange(N_R) / (N_R - 1))
    rr, aa = np.meshgrid(r_km * 1000.0, az, indexing="ij")
    gx = x0 + rr * (np.cos(aa) * fwd[0] + np.sin(aa) * right[0])
    gy = y0 + rr * (np.cos(aa) * fwd[1] + np.sin(aa) * right[1])
    # The spacing between neighbouring samples, across the fan and along it.
    dr = np.gradient(r_km * 1000.0)[:, None] * np.ones_like(rr)
    da = rr * np.radians(2 * HALF_DEG / (N_AZ - 1))
    spacing = np.maximum(dr, da)
    h = sample(levels, gx, gy, spacing)
    if np.isnan(h).any():
        raise SystemExit(f"the fan leaves the elevation model at {int(np.isnan(h).sum())} samples")
    z = h - (h_site + EYE_M) - rr**2 / (2.0 * R_MOON_M)

    # Sunlight: march toward the Sun from each sample; lit while no terrain on
    # the way stands above the Sun's line, softened over the Sun's own disc.
    sun_az = math.radians(SUN_REL_AZ_DEG)
    su = np.cos(sun_az) * fwd + np.sin(sun_az) * right
    steps = 60.0 * (40_000.0 / 60.0) ** (np.arange(110) / 109)  # 60 m to 40 km
    horizon = np.full(h.shape, -90.0)
    for s in steps:
        hs = sample(levels, gx + s * su[0], gy + s * su[1], spacing)
        ang = np.degrees(np.arctan2(hs - h - s * s / (2.0 * R_MOON_M), s))
        horizon = np.fmax(horizon, np.nan_to_num(ang, nan=-90.0))
    light = np.clip((SUN_EL_DEG - horizon) / 0.53 + 0.5, 0.0, 1.0)
    # The Sun's disc is half a degree wide, so a shadow cast kilometres away has
    # an edge tens of metres soft: two passes of a 3 x 3 mean give it that.
    for _ in range(2):
        p = np.pad(light, 1, mode="edge")
        light = (
            np.sum(
                [
                    p[1 + di : p.shape[0] - 1 + di, 1 + dj : p.shape[1] - 1 + dj]
                    for di in (-1, 0, 1)
                    for dj in (-1, 0, 1)
                ],
                axis=0,
            )
            / 9.0
        )
    skyline = float(np.degrees(np.arctan2(z[1:, N_AZ // 2], rr[1:, N_AZ // 2])).max())

    out.parent.mkdir(parents=True, exist_ok=True)
    header = np.array(
        [N_AZ, N_R, R0_KM, R1_KM, HALF_DEG, earth_el, SUN_REL_AZ_DEG, SUN_EL_DEG], dtype="<f4"
    )
    counts = np.round(z / (STEP_M + rr * STEP_PER_M))
    if np.abs(counts).max() > 32767:
        raise SystemExit("a height does not fit its 16 bits; widen the step")
    heights = counts.astype("<i2")
    with out.open("wb") as f:
        f.write(header.tobytes())
        f.write(heights.tobytes())
        f.write(np.round(light * 255).astype(np.uint8).tobytes())
    lat_e, lon_e = polar_to_geographic(
        np.array([x0 + 160_000 * fwd[0]]), np.array([y0 + 160_000 * fwd[1]])
    )
    print(
        f"wrote {out} ({out.stat().st_size // 1024} KB): site height {h_site:.0f} m, "
        f"Earth at {earth_el:.2f} deg, fan to {float(lat_e[0]):.2f} deg, "
        f"{float(lon_e[0]):.2f} deg; skyline toward Earth at {skyline:.2f} deg; "
        f"lit {float((light > 0.5).mean()) * 100:.0f}%"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=OUT)
    render(p.parse_args().out)


if __name__ == "__main__":
    main()
