"""Read the GRAIL GRGM1200A lunar gravity field (PDS Geosciences) to a chosen degree.

The file (``data/gravity/gggrx_1200a_sha.tab``, 84 MB) is ordered by degree,
so reading stops at the requested degree; the truncated field is cached as a
small ``.npz`` next to it. Header: reference radius (km), GM (km^3/s^2), GM
uncertainty, degree, order, normalisation flag (1 = fully normalised), and
the reference longitude and latitude. The field is in the Moon's principal
axes frame (MOON_PA), per its PDS label.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.core.gravity import Field

FILE = "gravity/gggrx_1200a_sha.tab"
SOURCE_URL = (
    "https://pds-geosciences.wustl.edu/grail/grail-l-lgrs-5-rdr-v1/grail_1001/shadr/"
    "gggrx_1200a_sha.tab"
)


class GravityMissing(FileNotFoundError):
    pass


def parse(lines: list[str], degree: int) -> Field:
    head = [x.strip() for x in lines[0].split(",")]
    radius_km, gm_km3 = float(head[0]), float(head[1])
    if int(head[5]) != 1:
        raise ValueError("GRGM1200A header does not say the coefficients are normalised")
    c = np.zeros((degree + 1, degree + 1))
    s = np.zeros((degree + 1, degree + 1))
    c[0, 0] = 1.0
    for ln in lines[1:]:
        parts = ln.split(",")
        n, m = int(parts[0]), int(parts[1])
        if n > degree:
            break
        c[n, m] = float(parts[2])
        s[n, m] = float(parts[3])
    return Field(gm=gm_km3 * 1e9, radius_m=radius_km * 1000.0, c=c, s=s, degree=degree)


@lru_cache(maxsize=4)
def moon_field(degree: int = 50) -> Field:
    root = get_settings().data_dir
    cache = root / "gravity" / f"grgm1200a_d{degree}.npz"
    if cache.exists():
        z = np.load(cache)
        return Field(float(z["gm"]), float(z["radius_m"]), z["c"], z["s"], degree)
    path = root / FILE
    if not path.exists():
        raise GravityMissing(f"{path} is missing (polar-data sync)")
    lines: list[str] = []
    with Path(path).open(encoding="ascii") as f:
        for ln in f:
            lines.append(ln)
            if len(lines) > 1:
                n = int(ln.split(",")[0])
                if n > degree:
                    break
    field = parse(lines, degree)
    np.savez(cache, gm=field.gm, radius_m=field.radius_m, c=field.c, s=field.s)
    return field
