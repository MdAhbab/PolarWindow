"""LRO Diviner Polar Resource Product: ground temperature near a site (ADR-21).

The product (``data/external/diviner_prp/dlre_prp_south.tab``, 605 MB, PDS
Geosciences, https://pds-geosciences.wustl.edu/lro/lro-l-dlre-5-prp-v1/) is a
triangulated mesh south of about 75.9 deg S. Each row is one triangle with its
vertices, centre longitude/latitude/altitude, the ANNUAL average temperature,
the annual maximum temperature and the ice-stability depth (-999 = none). It
has no time series.

``build`` streams the table once into a small ``.npz`` (triangle centres in the
lunar south polar stereographic grid, average, maximum, ice depth), cached at
``data/external/diviner_prp/index.npz`` and not in git. ``at`` answers "what are
the triangles within ``radius_m`` of this site": their median and their
minimum and maximum (the spread is the uncertainty), or None where the product
has no triangle that close (outside its coverage).

    python -m app.data.diviner build
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import numpy.typing as npt
from scipy.spatial import cKDTree

from app.config import get_settings
from app.core import projections

FloatArray = npt.NDArray[np.float64]

SOURCE_URL = "https://pds-geosciences.wustl.edu/lro/lro-l-dlre-5-prp-v1/"
TABLE = "external/diviner_prp/dlre_prp_south.tab"
INDEX = "external/diviner_prp/index.npz"
#: Columns of the table: tri_clon, tri_clat, tri_calt, temp_avg, temp_max, ice_depth.
_COLS = (9, 10, 11, 12, 13, 14)
_CHUNK_LINES = 200_000
NO_ICE = -999.0


class DivinerMissing(FileNotFoundError):
    pass


@dataclass(frozen=True, slots=True)
class Stat:
    """The median of the triangles within the radius, and their minimum and maximum."""

    median: float
    lo: float
    hi: float


@dataclass(frozen=True, slots=True)
class GroundTemps:
    temp_avg_k: Stat
    temp_max_k: Stat
    #: Median ice-stability depth of the triangles that have one, m; None if none does.
    ice_depth_m: float | None
    n_triangles: int
    radius_m: float
    source: str = SOURCE_URL


def _paths(index_path: Path | None, table_path: Path | None) -> tuple[Path, Path]:
    root = get_settings().data_dir
    return (index_path or root / INDEX), (table_path or root / TABLE)


def build(index_path: Path | None = None, table_path: Path | None = None) -> Path:
    """Stream the table into the compact index and return its path."""
    index, table = _paths(index_path, table_path)
    if not table.exists():
        raise DivinerMissing(f"{table} not found")
    parts: list[FloatArray] = []
    with table.open("r", encoding="ascii") as fh:
        fh.readline()  # header
        while True:
            lines = [ln for _, ln in zip(range(_CHUNK_LINES), fh, strict=False)]
            if not lines:
                break
            arr = np.loadtxt(lines, delimiter=",", usecols=_COLS, dtype=np.float64, ndmin=2)
            parts.append(arr)
    data = np.concatenate(parts) if parts else np.empty((0, 6))
    x, y = projections.geographic_to_polar(data[:, 0], data[:, 1])
    index.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        index,
        x=x.astype(np.float32),
        y=y.astype(np.float32),
        temp_avg=data[:, 3].astype(np.float32),
        temp_max=data[:, 4].astype(np.float32),
        ice_depth=data[:, 5].astype(np.float32),
    )
    _load.cache_clear()
    return index


@lru_cache(maxsize=2)
def _load(path: str) -> tuple[cKDTree, FloatArray, FloatArray, FloatArray]:
    p = Path(path)
    if not p.exists():
        raise DivinerMissing(f"{p} not found; run `python -m app.data.diviner build`")
    with np.load(p) as z:
        xy = np.column_stack([z["x"], z["y"]]).astype(np.float64)
        return (
            cKDTree(xy),
            z["temp_avg"].astype(np.float64),
            z["temp_max"].astype(np.float64),
            z["ice_depth"].astype(np.float64),
        )


def _stat(v: FloatArray) -> Stat:
    return Stat(float(np.median(v)), float(v.min()), float(v.max()))


def at(
    lat_deg: float, lon_deg: float, radius_m: float, *, index_path: Path | None = None
) -> GroundTemps | None:
    """Triangles whose centre is within ``radius_m`` of the point; None if there are none."""
    if radius_m <= 0:
        raise ValueError("radius must be positive")
    path, _ = _paths(index_path, None)
    tree, avg, tmax, ice = _load(str(path))
    x, y = projections.geographic_to_polar(np.array([lon_deg]), np.array([lat_deg]))
    idx = tree.query_ball_point([float(x[0]), float(y[0])], r=radius_m)
    if not idx:
        return None
    sel = np.asarray(idx, dtype=np.int64)
    ice_sel = ice[sel]
    ice_sel = ice_sel[ice_sel > NO_ICE + 1.0]
    return GroundTemps(
        temp_avg_k=_stat(avg[sel]),
        temp_max_k=_stat(tmax[sel]),
        ice_depth_m=float(np.median(ice_sel)) if ice_sel.size else None,
        n_triangles=int(sel.size),
        radius_m=float(radius_m),
    )


def main(argv: list[str]) -> int:
    if argv[:1] != ["build"]:
        print("usage: python -m app.data.diviner build")
        return 2
    print(f"wrote {build()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
