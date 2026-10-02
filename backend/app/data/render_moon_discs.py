"""Render the Missions page's two views of the whole Moon: the near side and the far side.

Each is the Moon seen from far away along its equator, centred on longitude
0 (the side that faces Earth) and on longitude 180: an orthographic view, the
projection the page's pins use, so a pin at a published latitude and longitude
lands on the place it names.

The picture is NASA's LRO wide-angle camera mosaic (the same file the front
page's globe wears: equirectangular, longitude -180 to 180 left to right,
latitude 90 to -90 top to bottom). The mosaic is taken under a high Sun, so
the discs show the ground's own brightness, the dark maria and the bright
highlands, with no shadow side.

Output: two square JPEGs, the disc touching each edge, the corners black.

Run: ``uv run python -m app.data.render_moon_discs``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image

SPACE = Path(__file__).resolve().parents[3] / "frontend" / "src" / "assets" / "space"
MOSAIC = SPACE / "moon-lro-wac-2048.jpg"
SIZE = 640


def disc(mosaic: npt.NDArray[np.float64], lon0_deg: float, size: int = SIZE) -> Image.Image:
    """The hemisphere centred on (0 deg N, ``lon0_deg`` E), north up, east to the right."""
    h, w = mosaic.shape[:2]
    # Pixel centres across the disc, -1 to 1; y up.
    c = (np.arange(size) + 0.5) / size * 2.0 - 1.0
    x, y = np.meshgrid(c, -c)
    rr = x * x + y * y
    inside = rr <= 1.0
    z = np.sqrt(np.clip(1.0 - rr, 0.0, 1.0))
    lat = np.arcsin(np.clip(y, -1.0, 1.0))
    lon = np.radians(lon0_deg) + np.arctan2(x, z)
    # Where that is in the mosaic, read between its four nearest pixels.
    u = ((np.degrees(lon) + 180.0) % 360.0) / 360.0 * w - 0.5
    v = (90.0 - np.degrees(lat)) / 180.0 * h - 0.5
    u0 = np.floor(u).astype(int)
    v0 = np.clip(np.floor(v).astype(int), 0, h - 2)
    fu = (u - u0)[..., None]
    fv = np.clip(v - v0, 0.0, 1.0)[..., None]
    a = mosaic[v0, u0 % w]
    b = mosaic[v0, (u0 + 1) % w]
    cc = mosaic[v0 + 1, u0 % w]
    d = mosaic[v0 + 1, (u0 + 1) % w]
    out = (a * (1 - fu) + b * fu) * (1 - fv) + (cc * (1 - fu) + d * fu) * fv
    # A soft edge one pixel wide, so the limb is not a staircase.
    edge = np.clip((1.0 - np.sqrt(rr)) * size / 2.0, 0.0, 1.0)[..., None]
    out = np.where(inside[..., None], out * edge, 0.0)
    return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8))


def main() -> None:
    mosaic = np.asarray(Image.open(MOSAIC).convert("RGB"), dtype=np.float64)
    for name, lon0 in (("near", 0.0), ("far", 180.0)):
        out = SPACE / f"moon-{name}-side-{SIZE}.jpg"
        disc(mosaic, lon0).save(out, quality=84, optimize=True, progressive=True)
        print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
