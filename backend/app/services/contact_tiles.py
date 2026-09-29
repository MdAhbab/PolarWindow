"""Contact map tiles (F5): the rover line of sight as raster tiles.

A rover answer holds the states of a viewshed around the lander (72 bearings by
20 ranges). This module draws them as 256 px PNG tiles in the terrain tiles' own
scheme (a quadtree over the regional elevation model's extent, in the lunar south
polar stereographic grid), so a map can lay them over the hillshade with the same
arithmetic. It reuses the tile pipeline rather than adding one: ``TileGrid`` for
where a tile is, ``render_layer`` for the terrain's look, ``write_png`` to write it,
and the same on-disk cache with atomic writes, rendered off the event loop.

The tiles belong to one stored answer (the assessment's id is in the URL), so they
never change: a new answer has a new id. Three layers:

* ``sight`` and ``radio``: the answer's line of sight and radio path, each cell clear,
  blocked or uncertain, drawn by :func:`app.core.viewshed.tile_rgba`;
* ``terrain``: the hillshade of the elevation model the answer used, the 20 m polar
  window around the landing spot where there is one. The regional 80 m model the
  terrain tiles are made from is too coarse at the zoom of a rover map (its posts are
  bigger than the lander's whole neighbourhood).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import viewshed
from app.core.projections import local_frame
from app.data.lola import DemTile
from app.data.render_tiles import TILE_PX, TileGrid, render_layer, write_png
from app.db.repositories.jobs import AssessmentRepository
from app.services import tile_service
from app.services.tile_service import DemMissing, OutOfScheme, Tile, UnknownLayer

#: A rover map is drawn at the size of the lander's neighbourhood: a 50 m radius at 1 m a
#: pixel is zoom 13, but no elevation model has more to show, so the scheme stops at 12
#: (0.6 m a pixel), where the terrain tiles stop at 7.
MAX_ZOOM: Final[int] = 12
LAYERS: Final[tuple[str, ...]] = ("terrain", "sight", "radio")

_STATES: Final[dict[str, int]] = {
    "blocked": viewshed.BLOCKED,
    "uncertain": viewshed.UNCERTAIN,
    "clear": viewshed.CLEAR,
}


class NoViewshed(LookupError):
    """There is no such answer, or it has no map to draw; the message says which."""


def url_template(assessment_id: int) -> str:
    """The tile URL of an answer, under the API's prefix: ``{z}``, ``{x}`` and ``{y}`` are
    filled in by the map, and ``?layer=`` picks ``terrain``, ``sight`` (default) or ``radio``."""
    return f"/tiles/viewshed/{assessment_id}/{{z}}/{{x}}/{{y}}.png"


def validate(layer: str, z: int, x: int, y: int) -> None:
    if layer not in LAYERS:
        raise UnknownLayer(f"'{layer}' is not a layer here. Available: {', '.join(LAYERS)}.")
    if not (0 <= z <= MAX_ZOOM) or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise OutOfScheme(f"z{z} has {2**z} tiles per axis; ({x}, {y}) is outside it.")


@lru_cache(maxsize=1)
def _half_extent_m(regional: Path) -> float:
    """The tile scheme's half side: the regional model's own extent (read without loading it)."""
    with np.load(regional, allow_pickle=False) as z:
        return abs(float(z["origin_x_m"]))


@lru_cache(maxsize=2)
def _window(path: Path) -> DemTile:
    return DemTile.load(path)


def _terrain(site_id: str | None) -> DemTile:
    """The elevation model the rover job read: the site's 20 m window, else the regional one
    (the terrain tiles' own copy, so the 230 MB is held once)."""
    s = get_settings()
    fine = s.fine_dem_path(site_id) if site_id else None
    if fine is not None and fine.exists():
        return _window(fine)
    if not s.regional_dem_path.exists():
        raise DemMissing(f"The regional elevation model is not present at {s.regional_dem_path}.")
    return tile_service._regional(s.regional_dem_path)


def _states(grid: list[list[str]]) -> npt.NDArray[np.int8]:
    return np.array([[_STATES[w] for w in row] for row in grid], dtype=np.int8)


def _render(
    layer: str, params: dict[str, Any], vs: dict[str, Any], z: int, x: int, y: int
) -> npt.NDArray[np.uint8] | None:
    s = get_settings()
    grid = TileGrid(half_extent_m=_half_extent_m(s.regional_dem_path))
    bounds = grid.bounds(z, x, y)
    if layer == "terrain":
        return render_layer("hillshade", _terrain(params.get("site_id")), bounds)
    frame = local_frame(float(params["lon_deg"]), float(params["lat_deg"]))
    return viewshed.tile_rgba(
        bounds,
        frame,
        np.asarray(vs["bearings_deg"], dtype=np.float64),
        np.asarray(vs["ranges_m"], dtype=np.float64),
        _states(vs[layer]),
        pixel_origin=(x * TILE_PX, y * TILE_PX),
    )


def _render_to_disk(
    layer: str, params: dict[str, Any], vs: dict[str, Any], z: int, x: int, y: int, path: Path
) -> bool:
    """Render one tile and write it atomically. False when nothing is drawn in it."""
    rgba = _render(layer, params, vs, z, x, y)
    if rgba is None:
        return False
    # A name of its own: two requests for one missing tile both render it, and the last
    # to finish wins with the same picture.
    tmp = path.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex[:8]}.part")
    write_png(tmp, rgba)
    tmp.replace(path)
    return True


def _etag(blob: bytes) -> str:
    return f'W/"{hashlib.sha256(blob).hexdigest()[:16]}"'


async def get_tile(
    session: AsyncSession, assessment_id: int, layer: str, z: int, x: int, y: int
) -> Tile:
    """The tile, or ``blob=None`` where the layer draws nothing (inside the grid, no data)."""
    validate(layer, z, x, y)
    rec = await AssessmentRepository(session).get(assessment_id)
    if rec is None or rec.kind != "rover":
        raise NoViewshed("No line-of-sight answer has this number.")
    data = rec.result.get("data") or {}
    vs = data.get("viewshed")
    if vs is None:
        raise NoViewshed(
            data.get("reason")
            or "This answer has no map: the ground around the lander is not known."
        )
    s = get_settings()
    path = s.tile_dir / "viewshed" / str(assessment_id) / layer / str(z) / str(x) / f"{y}.png"
    source = "static"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not await asyncio.to_thread(_render_to_disk, layer, rec.params, vs, z, x, y, path):
            return Tile(blob=None, etag=None, source="empty")
        source = "dynamic"
    blob = await asyncio.to_thread(path.read_bytes)
    return Tile(blob=blob, etag=_etag(blob), source=source)
