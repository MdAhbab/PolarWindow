"""Map tiles of a rover line-of-sight answer (F5): the viewshed over the terrain.

Same scheme as ``/tiles/{layer}/{z}/{x}/{y}.png`` (a quadtree over the regional elevation
model's extent in the south polar stereographic grid, 256 px PNG), so a map lays them over
the hillshade with the same arithmetic. The tiles belong to one stored answer, whose id is in
the path (``viewshed_tile`` in the answer gives the URL): they never change.

* **200**: the tile.
* **204**: inside the grid, but the layer draws nothing there (most tiles of the grid).
* **404**: no such answer or no map in it; a layer or z/x/y outside the scheme.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi import Path as PathParam

from app.api.v1 import deps
from app.services import contact_tiles, tile_service

router = APIRouter(prefix="/tiles/viewshed", tags=["tiles"])


@router.get(
    "/{assessment_id}/{z}/{x}/{y}.png",
    summary="A rover line-of-sight answer as map tiles, or the terrain under it",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}, "description": "Tile image."},
        204: {"description": "Inside the grid, but nothing is drawn there."},
        404: {"description": "No such answer or no map in it, or z/x/y outside the tile scheme."},
    },
)
async def get_viewshed_tile(
    request: Request,
    assessment_id: int = PathParam(ge=1, description="The answer's number, from `viewshed_tile`."),
    z: int = PathParam(ge=0, le=contact_tiles.MAX_ZOOM),
    x: int = PathParam(ge=0),
    y: int = PathParam(ge=0),
    layer: str = Query(
        "sight",
        description="`sight` (line of sight), `radio` (the radio path too) or `terrain` (the "
        "hillshade of the elevation model the answer used).",
    ),
    session: Any = Depends(deps.db),
) -> Response:
    try:
        tile = await contact_tiles.get_tile(session, assessment_id, layer, z, x, y)
    except contact_tiles.NoViewshed as exc:
        raise deps.problem(
            404,
            "no-viewshed",
            "No line-of-sight map here",
            str(exc),
            "The answer's numbers and its table are unaffected.",
        ) from exc
    except tile_service.UnknownLayer as exc:
        raise deps.problem(
            404,
            "unknown-layer",
            "No such map layer",
            str(exc),
            "The other layers are unaffected.",
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
            "The line-of-sight layers are unaffected; only the terrain under them is missing.",
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
            # The answer is in the path, so a tile never changes.
            "Cache-Control": "public, max-age=86400",
            "X-Tile-Source": tile.source,
        },
    )
