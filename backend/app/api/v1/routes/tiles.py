"""Raster tile serving.

ADR-4: tiles are pre-rendered at seed time and served as static files. The
render-on-demand safety net for an incomplete seed lives in
``services.tile_service``, off the event loop and one render per tile.

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

from fastapi import APIRouter, Request, Response
from fastapi import Path as PathParam

from app.api.v1 import deps
from app.services import tile_service

router = APIRouter(prefix="/tiles", tags=["tiles"])


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
    z: int = PathParam(ge=0, le=tile_service.MAX_ZOOM),
    x: int = PathParam(ge=0),
    y: int = PathParam(ge=0),
) -> Response:
    try:
        tile = await tile_service.get_tile(layer, z, x, y)
    except tile_service.UnknownLayer as exc:
        raise deps.problem(
            404,
            "unknown-layer",
            "No such map layer",
            str(exc),
            "The other layers and every non-map view are unaffected.",
        ) from exc
    except tile_service.OutOfScheme as exc:
        raise deps.problem(
            404,
            "tile-out-of-scheme",
            "Tile outside the scheme",
            str(exc),
            "Other tiles are unaffected.",
        ) from exc
    except tile_service.DemMissing as exc:
        raise deps.problem(
            503,
            "dem-missing",
            "Terrain data is not loaded",
            str(exc),
            "Site metrics, timelines and comparisons are unaffected; only the "
            "map's terrain layers are missing.",
            retryable=True,
            action="Run make seed",
        ) from exc

    if tile.blob is None:
        return Response(status_code=204, headers={"X-Tile-Source": tile.source})
    if request.headers.get("if-none-match") == tile.etag:
        return Response(status_code=304, headers={"ETag": tile.etag or ""})
    return Response(
        content=tile.blob,
        media_type="image/png",
        headers={
            "ETag": tile.etag or "",
            # Tiles are immutable for a data release; the version is in the
            # deploy, not the URL, so a long max-age with an ETag is the right
            # trade for a demo.
            "Cache-Control": "public, max-age=86400",
            "X-Tile-Source": tile.source,
            "X-Tile-Note": tile_service.TILE_NOTE,
        },
    )


# The brief's contract spells the path without a suffix. Both spellings serve
# the same tile; the suffixed one stays the canonical URL the frontend uses.
router.add_api_route(
    "/{layer}/{z}/{x}/{y}",
    get_tile,
    methods=["GET"],
    name="get_tile_unsuffixed",
    summary="Same tile as the .png route, for clients that omit the suffix",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}, 204: {"description": "No data here."}},
)
