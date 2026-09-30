"""Raster tile lookup and the render-on-demand safety net.

ADR-4 pre-renders the pyramid at seed time; this module is what the route
delegates to so that the HTTP layer never touches the data layer directly, and
so the fallback path is fit to run inside an async server:

* **The regional DEM is loaded once.** It is ~115 MB; the previous fallback
  re-read it for *every* missing tile, so a first map view against an
  unrendered pyramid read it thirty times over.
* **Rendering happens on a worker thread**, not on the event loop. A tile
  render is tens of milliseconds of numpy; on the loop it stalls every other
  request -- including the date slider's cache hits -- for its duration.
* **One render per tile.** Concurrent requests for the same missing tile wait
  on a per-tile lock and then read the file the winner wrote.
* **Writes are atomic** (temp file + rename), so a reader never sees half a PNG.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from app.config import get_settings
from app.data.lola import DemTile
from app.data.render_tiles import LAYERS, TileGrid, render_layer, write_png

MAX_ZOOM: Final[int] = 7
TILE_NOTE: Final[str] = (
    "illumination and psr are approximations from a ring-based horizon proxy, not "
    "published products"
)


class UnknownLayer(LookupError):
    pass


class OutOfScheme(LookupError):
    pass


class DemMissing(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Tile:
    """A tile ready to serve, or ``blob=None`` for "inside the grid, no data"."""

    blob: bytes | None
    etag: str | None
    source: str


def validate(layer: str, z: int, x: int, y: int) -> None:
    if layer not in LAYERS:
        raise UnknownLayer(f"'{layer}' is not a layer. Available: {', '.join(LAYERS)}.")
    if not (0 <= z <= MAX_ZOOM) or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise OutOfScheme(f"z{z} has {2**z} tiles per axis; ({x}, {y}) is outside it.")


@lru_cache(maxsize=1)
def _regional(path: Path) -> DemTile:
    return DemTile.load(path)


_locks: dict[tuple[str, int, int, int], asyncio.Lock] = {}


def etag(blob: bytes) -> str:
    """The weak entity tag of a tile's bytes, for ``If-None-Match``."""
    return f'W/"{hashlib.sha256(blob).hexdigest()[:16]}"'


def _render_to_disk(layer: str, z: int, x: int, y: int, path: Path) -> bool:
    """Render one tile and write it atomically. False when it has no data."""
    s = get_settings()
    dem = _regional(s.regional_dem_path)
    grid = TileGrid(half_extent_m=abs(dem.origin_x_m))
    rgba = render_layer(layer, dem, grid.bounds(z, x, y))
    if rgba is None:
        return False
    tmp = path.with_suffix(f".{os.getpid()}.part")
    write_png(tmp, rgba)
    tmp.replace(path)
    return True


async def get_tile(layer: str, z: int, x: int, y: int) -> Tile:
    validate(layer, z, x, y)
    s = get_settings()
    path = s.tile_dir / layer / str(z) / str(x) / f"{y}.png"
    source = "static"

    if not path.exists():
        if not s.regional_dem_path.exists():
            raise DemMissing(
                f"The regional elevation model is not present at {s.regional_dem_path}."
            )
        key = (layer, z, x, y)
        lock = _locks.setdefault(key, asyncio.Lock())
        async with lock:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                rendered = await asyncio.to_thread(_render_to_disk, layer, z, x, y, path)
                if not rendered:
                    _locks.pop(key, None)
                    return Tile(blob=None, etag=None, source="empty")
                source = "dynamic"
        _locks.pop(key, None)

    blob = await asyncio.to_thread(path.read_bytes)
    return Tile(blob=blob, etag=etag(blob), source=source)
