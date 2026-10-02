"""Fetch the photograph the Map and Missions pages draw under their pins: the south pole.

The picture is NASA's LRO wide-angle camera mosaic of the south pole
(``LRO_WAC_Mosaic_SPole60_100m_v02``, public domain), read from NASA's Moon
Trek tile service. It is in the south polar stereographic projection the LOLA
products and this project's own tiles use (the pole at the centre, longitude
0 toward the top, 90 deg E to the right), so it is cut to the square the tile
pyramid covers (``TILE_HALF_EXTENT_M`` each way, which holds the circle at
80 deg S) with no reprojection: a pin at a published latitude and longitude
lands on the place it names.

It is a photograph, so its shadows are those of the days the pictures were
taken, and the craters the Sun never reaches are black. The page lays the
LOLA relief into those shadows and says under the map that the picture's
light is not that of the chosen dates.

Tiles at the service's finest level are 267.56 m to a pixel; 100 of them
(about 5 MB) cover the square, which is saved as one JPEG.

Run: ``uv run python -m app.data.fetch_pole_mosaic``
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

from PIL import Image

LAYER = "LRO_WAC_Mosaic_SPole60_100m_v02"
URL = (
    "https://trek.nasa.gov/tiles/Moon/SP/"
    + LAYER
    + "/1.0.0/default/default028mm/{z}/{row}/{col}.png"
)
ZOOM = 5
#: The tile grid's corner (metres) and its pixel size at ZOOM: the scale denominator times 0.28 mm.
ORIGIN_M = 1_095_930.0
PIXEL_M = 9.5557512555803440e05 * 0.00028
TILE_PX = 256
#: Half the side of this project's own tile pyramid (frontend PolarMap, backend render_tiles).
TILE_HALF_EXTENT_M = 303_960.0
SIZE = 2048

OUT = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "assets"
    / "space"
    / f"moon-south-pole-wac-{SIZE}.jpg"
)


def fetch(out: Path = OUT) -> None:
    left = (ORIGIN_M - TILE_HALF_EXTENT_M) / PIXEL_M
    side = 2 * TILE_HALF_EXTENT_M / PIXEL_M
    first = int(left // TILE_PX)
    last = int((left + side) // TILE_PX)
    n = last - first + 1
    sheet = Image.new("L", (n * TILE_PX, n * TILE_PX))
    got = 0
    for row in range(first, last + 1):
        for col in range(first, last + 1):
            with urllib.request.urlopen(URL.format(z=ZOOM, row=row, col=col), timeout=60) as r:
                data = r.read()
            got += len(data)
            tile = Image.open(io.BytesIO(data)).convert("L")
            sheet.paste(tile, ((col - first) * TILE_PX, (row - first) * TILE_PX))
    x0 = left - first * TILE_PX
    cut = sheet.resize((SIZE, SIZE), Image.Resampling.LANCZOS, box=(x0, x0, x0 + side, x0 + side))
    out.parent.mkdir(parents=True, exist_ok=True)
    cut.save(out, quality=84, optimize=True, progressive=True)
    print(
        f"read {n * n} tiles ({got // 1024} KB) of {LAYER}; "
        f"wrote {out} ({out.stat().st_size // 1024} KB, {SIZE} px, "
        f"{2 * TILE_HALF_EXTENT_M / SIZE:.0f} m to a pixel)"
    )


if __name__ == "__main__":
    fetch()
