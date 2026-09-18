"""Raster tile serving.

ADR-4: tiles are pre-rendered at seed time and served as static files. The
dynamic branch below is a safety net for an incomplete seed, not the primary
path -- it calls the same renderer the seed script does, so the two cannot
drift.

Three response cases, and the distinction between the last two matters:

* **200** -- the tile exists (or was rendered on demand).
* **204** -- the tile is inside the grid but has no data there. Not a 404: the
  map requests a rectangular grid of tiles and the corners of a polar scene are
  legitimately empty. A wall of 404s in the network panel during a demo reads
  as a broken product.
* **404** -- the layer or the z/x/y is outside the scheme entirely. That is a
  genuine client error.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from fastapi import Path as PathParam

from app.api.v1 import deps
from app.config import Settings
from app.data.render_tiles import LAYERS, TileGrid, render_layer, write_png

router = APIRouter(prefix="/tiles", tags=["tiles"])

MAX_ZOOM = 7


@router.get(
    "/{layer}/{z}/{x}/{y}.png",
    summary="Terrain hillshade, approximate illumination and approximate PSR",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}, "description": "Tile image."},
        204: {"description": "Inside the grid, but no data there."},
        404: {"description": "Unknown layer, or z/x/y outside the tile scheme."},
    },
)
async def get_tile(
    request: Request,
    layer: str = PathParam(description="One of hillshade, illumination, psr."),
    z: int = PathParam(ge=0, le=MAX_ZOOM),
    x: int = PathParam(ge=0),
    y: int = PathParam(ge=0),
    s: Settings = Depends(deps.settings),
) -> Response:
    if layer not in LAYERS:
        raise deps.problem(
            404,
            "unknown-layer",
            "No such map layer",
            f"'{layer}' is not a layer. Available: {', '.join(LAYERS)}.",
            "The other layers and every non-map view are unaffected.",
        )
    if not (0 <= x < 2**z and 0 <= y < 2**z):
        raise deps.problem(
            404,
            "tile-out-of-scheme",
            "Tile outside the scheme",
            f"z{z} has {2**z} tiles per axis; ({x}, {y}) is outside it.",
            "Other tiles are unaffected.",
        )

    path: Path = s.tile_dir / layer / str(z) / str(x) / f"{y}.png"
    source = "static"

    if not path.exists():
        # Safety net for an incomplete seed. Same renderer as the seed script,
        # written through to disk so the cost is paid once.
        from app.data.lola import DemTile

        if not s.regional_dem_path.exists():
            raise deps.problem(
                503,
                "dem-missing",
                "Terrain data is not loaded",
                f"The regional elevation model is not present at {s.regional_dem_path}.",
                "Site metrics, timelines and comparisons are unaffected; only the "
                "map's terrain layers are missing.",
                retryable=True,
                action="Run make seed",
            )
        tile_data = DemTile.load(s.regional_dem_path)
        grid = TileGrid(half_extent_m=abs(tile_data.origin_x_m))
        rgba = render_layer(layer, tile_data, grid.bounds(z, x, y))
        if rgba is None:
            return Response(status_code=204, headers={"X-Tile-Source": "empty"})
        write_png(path, rgba)
        source = "dynamic"

    blob = path.read_bytes()
    etag = f'W/"{hashlib.sha256(blob).hexdigest()[:16]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    return Response(
        content=blob,
        media_type="image/png",
        headers={
            "ETag": etag,
            # Tiles are immutable for an engine version; the version is in the
            # deploy, not the URL, so a long max-age with an ETag is the right
            # trade for a demo.
            "Cache-Control": "public, max-age=86400",
            "X-Tile-Source": source,
            "X-Tile-Note": (
                "illumination and psr are approximations from a ring-based horizon "
                "proxy, not published products"
            ),
        },
    )
