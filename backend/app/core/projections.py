"""Lunar south polar stereographic <-> selenographic, via pyproj.

One projection and one raster read is all this product needs, which is why
pyproj + rasterio is the right weight here and geopandas is not.

The CRS is built explicitly rather than by EPSG code. There is no EPSG code for
a lunar south polar stereographic on the 1737.4 km sphere that is stable across
PROJ versions, and silently picking a near-match would put every site tens of
metres from where it belongs -- which at a 20 m DEM post spacing is a real
error, not a rounding one.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Final

import numpy as np
import numpy.typing as npt
from pyproj import CRS, Transformer

FloatArray = npt.NDArray[np.float64]

#: Volumetric mean radius of the Moon, metres. Must match core.spice.R_MOON_M
#: and the frontend's R_MOON; a mismatch shows up as a curvature-drop
#: disagreement that is invisible until the golden tests catch it.
R_MOON_M: Final[float] = 1_737_400.0

#: Geographic CRS on the lunar sphere, longitudes east, latitudes planetocentric.
MOON_GEOGRAPHIC: Final[str] = f"+proj=longlat +R={R_MOON_M} +no_defs +type=crs"

#: South polar stereographic, exactly as the LOLA polar GDR products ship.
#:
#: Verified against the PDS label of LDEM_80S_20M, not assumed: that product
#: declares MAP_RESOLUTION = 1516.17 pix/deg at MAP_SCALE = 20 m/pix, and
#: 1737.4 km * pi/180 / 20 m = 1516.17 -- which is scale true at the **pole**
#: (k_0 = 1 at lat_0), not at a standard parallel. An earlier draft of this file
#: assumed lat_ts = -87.5 by analogy with terrestrial polar products; that would
#: have put every site ~0.2 % off in range, which at 20 m posts is metres of
#: horizontal error and a real shift in where a ridge sits.
MOON_SOUTH_POLAR: Final[str] = (
    f"+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 "
    f"+R={R_MOON_M} +units=m +no_defs +type=crs"
)


@lru_cache(maxsize=4)
def _transformer(src: str, dst: str) -> Transformer:
    """Transformers are expensive to build and safe to reuse; cache them."""
    return Transformer.from_crs(CRS.from_proj4(src), CRS.from_proj4(dst), always_xy=True)


def geographic_to_polar(lon_deg: FloatArray, lat_deg: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Selenographic (lon, lat) -> south polar stereographic (x, y) in metres."""
    t = _transformer(MOON_GEOGRAPHIC, MOON_SOUTH_POLAR)
    x, y = t.transform(np.asarray(lon_deg, dtype=np.float64), np.asarray(lat_deg, dtype=np.float64))
    return np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)


def polar_to_geographic(x_m: FloatArray, y_m: FloatArray) -> tuple[FloatArray, FloatArray]:
    """South polar stereographic (x, y) -> selenographic (lon, lat) in degrees."""
    t = _transformer(MOON_SOUTH_POLAR, MOON_GEOGRAPHIC)
    lon, lat = t.transform(np.asarray(x_m, dtype=np.float64), np.asarray(y_m, dtype=np.float64))
    return np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class LocalFrame:
    """A site's local tangent plane, anchored in the polar stereographic grid.

    The horizon ray-march works in local east/north metres because that is the
    frame the azimuths are defined in. Near the south pole, grid north in a
    polar stereographic projection is *not* true north -- it rotates with
    longitude -- so a ray-march done directly in grid coordinates would report
    every blocker at the wrong bearing, by an amount equal to the site's
    longitude. That is a 166 deg error at Shackleton. This class carries the
    rotation that prevents it.
    """

    lon_deg: float
    lat_deg: float
    x0_m: float
    y0_m: float
    #: Angle from grid +y (grid north) to true north, radians, at this site.
    grid_convergence_rad: float

    def local_to_grid(
        self, east_m: FloatArray, north_m: FloatArray
    ) -> tuple[FloatArray, FloatArray]:
        """Local ENU metres (true-north referenced) -> polar stereographic metres."""
        c = np.cos(self.grid_convergence_rad)
        s = np.sin(self.grid_convergence_rad)
        gx = self.x0_m + east_m * c + north_m * s
        gy = self.y0_m - east_m * s + north_m * c
        return gx, gy


def local_frame(lon_deg: float, lat_deg: float) -> LocalFrame:
    """Build a site's local frame, measuring grid convergence numerically.

    Measured rather than derived from the closed form, because the closed form
    depends on the projection's ``lon_0`` and sign conventions and getting it
    subtly wrong is easy and silent. Stepping a small distance due north and
    seeing where it lands in the grid is self-evidently correct and costs two
    transforms, once per site.
    """
    x0, y0 = geographic_to_polar(np.array([lon_deg]), np.array([lat_deg]))
    # 100 m due north in latitude.
    dlat = np.degrees(100.0 / R_MOON_M)
    x1, y1 = geographic_to_polar(np.array([lon_deg]), np.array([lat_deg + dlat]))
    dx = float(x1[0] - x0[0])
    dy = float(y1[0] - y0[0])
    convergence = float(np.arctan2(dx, dy))
    return LocalFrame(
        lon_deg=lon_deg,
        lat_deg=lat_deg,
        x0_m=float(x0[0]),
        y0_m=float(y0[0]),
        grid_convergence_rad=convergence,
    )
