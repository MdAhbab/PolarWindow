# ADR-4: Pre-render static PNG tiles at seed time; keep rio-tiler as the builder

**Status:** Accepted
**Date:** 2026-09-18
**Deciders:** backend lead
**Relates to:** §7 of the brief, N3 (cold start < 20 s), ADR-1

## Context

`GET /tiles/{layer}/{z}/{x}/{y}` serves three raster layers behind the map
screen: `hillshade` (terrain relief), `illumination` (average sunlit fraction),
and `psr` (permanently shadowed regions). The source is the LOLA south polar
DEM in south polar stereographic projection.

What the map actually needs is narrower than a general tile service, and that
narrowness is the whole decision:

- **The extent is fixed.** `PolarMap` draws roughly a 300 km box around the
  south pole. Not a world map — one scene.
- **The zoom range is small.** The map is not deeply zoomable; z0–z5 over that
  extent is plenty, and the frontend's own comment already concedes the map's
  hillshade is schematic and covers a different scale than the per-site DEM.
- **The data never changes.** The DEM is a static published product. There is no
  time dimension, no user-supplied raster, no dynamic band math driven by a UI
  control.
- **There is no basemap service to fall back on.** There is no OpenStreetMap for
  the Moon, so whatever we build is the only thing on screen.

Counting tiles for a fixed extent at z0–z5 in a polar stereographic tile matrix:
1 + 4 + 16 + 64 + 256 + 1024 = 1,365 tiles per layer, and the polar extent
clips a large fraction of the outer levels. Three layers ⇒ **under 4,100 tiles,
realistically ~2,500 after clipping, ~20–60 KB each ⇒ well under 150 MB.**

That number is what makes this decision easy, and it is worth stating before the
options rather than after: the entire tile pyramid is smaller than the SPICE
kernels we already ship.

## Decision

**Pre-render the full pyramid at seed time using rio-tiler + morecantile, write
PNGs to `data/tiles/{layer}/{z}/{x}/{y}.png`, and serve them as static files**
with long-lived `Cache-Control` and an `ETag`.

The FastAPI route remains `GET /api/v1/tiles/{layer}/{z}/{x}/{y}.png`, so the
API contract does not depend on the implementation:

- tile exists on disk → stream it, `Cache-Control: public, max-age=31536000, immutable`
- tile is outside the rendered extent → **204 No Content**, not 404. The map
  requests a grid; an out-of-extent tile is an expected, non-erroneous answer,
  and 404s in the network panel during a demo look like a bug.
- tile missing but in extent → render on demand via rio-tiler, write through to
  disk, serve. This is a safety net for a partial seed, not the primary path,
  and it sets `meta`-equivalent header `X-Tile-Source: dynamic`.

So rio-tiler is a **build-time dependency that also happens to be a runtime
fallback**, rather than a request-path service. `make seed` renders the pyramid;
`make tiles` re-renders one layer.

`psr` deserves a note: it is rendered from the illumination raster by threshold,
and a permanently-shadowed region is a *claim about many years*, not about the
demo window. The layer is labelled from the source product and the legend says
so, because presenting a thresholded single-window illumination as "PSR" would
be exactly the kind of quiet overstatement rule 10 forbids.

## Options Considered

### Option A (chosen): Pre-rendered static PNGs, rio-tiler at build time

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low at runtime; a seed script to write |
| Cold start | **Zero** — no raster opened at boot |
| Latency | ~1 ms, it is a file read |
| Storage | ~150 MB |
| Flexibility | Poor — a colour-ramp change means re-rendering |

**Pros:** the request path has no GDAL in it, so the failure modes of GDAL
(missing PROJ data, a driver mismatch in the container, a corrupt overview) move
from *runtime, during the demo* to *build time, on my machine, with a log*. Tiles
can be served by nginx or a CDN with no code change. Panning the map cannot be
made slow by a cold raster handle. Deterministic and diffable.
**Cons:** ~150 MB in the image or volume; changing the hillshade azimuth or the
illumination ramp is a re-render (minutes, offline); genuinely dynamic band math
is impossible.

### Option B: Dynamic rio-tiler on every request

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low to start, medium to make fast |
| Cold start | **Poor** — first tile opens the COG, builds overviews, warms PROJ |
| Latency | 40–200 ms warm, seconds cold |
| Storage | Zero beyond the DEM |
| Flexibility | Excellent |

**Pros:** no seed step; the DEM is the single source of truth; a colour ramp or
a hillshade angle can become a query parameter; nothing to invalidate.
**Cons:** three that matter here. (i) **Cold start.** The map screen requests
~30 tiles at once on first paint; if each opens a raster window and the process
has just started, the first impression of the product is a map filling in
tile-by-tile over several seconds. N3 exists to prevent exactly that. (ii) GDAL
in the request path is the least predictable dependency in the stack, and its
problems surface as 500s under load rather than at boot. (iii) It puts CPU-heavy
synchronous work into the async API process, competing with the SPICE thread and
the timeline computation for the same cores during the same interaction — the
user pans the map *and* drags the slider.

### Option C: Dynamic with a disk/Redis cache in front

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Cold start | Poor on first visit, good after |
| Latency | 1 ms warm, 200 ms cold |
| Storage | Converges on Option A's |
| Flexibility | Good |

**Pros:** the honest middle; only renders what is actually looked at; keeps the
flexibility of B for tiles nobody requests.
**Cons:** it converges on Option A's storage while keeping B's cold-start
problem for the first viewer of every tile — and in a demo, **every viewer is
the first viewer**. It also adds a cache-invalidation concern that Option A does
not have. This is the classic case where the lazy variant costs more than the
eager one because the access pattern is small, known and exhaustive.

### Option D: Ship vector outlines instead of rasters

Briefly considered: crater rims and PSR polygons as GeoJSON, drawn by the client.
Much smaller, infinitely scalable, and it would suit the product's low-chroma
schematic style. Rejected because hillshade is the one layer that genuinely needs
a raster, and having two delivery mechanisms for one map is more complexity than
150 MB of PNGs. Worth revisiting if the map ever needs true deep zoom.

## Trade-off Analysis

The general-purpose answer to raster tiling is Option B, and it is general-purpose
for good reasons — in a system where users upload rasters, or choose band
combinations, or the data updates, pre-rendering is untenable.

None of those conditions hold. The extent is fixed, the data is static, the zoom
range is shallow, and the whole pyramid is ~150 MB. When the output space of a
dynamic service is small enough to enumerate, enumerating it converts a
latency-and-reliability problem into a storage problem, and storage is the
cheapest thing here.

The hackathon time budget points the same way, which is unusual and worth
naming: the seed script is ~80 lines of rio-tiler, while making Option B
demo-reliable means warming caches, tuning GDAL env vars, moving work off the
event loop and testing under concurrent pan-plus-drag. The eager option is both
faster to build *and* faster to run. The only thing it costs is flexibility we
have no requirement for.

The 204-vs-404 detail is small but deliberate: it is the difference between a
network panel that looks calm and one that looks broken while someone is being
shown the product.

## Consequences

**Easier**
- Cold start is unaffected by tiles. The API process never opens a raster on a
  request unless the seed was incomplete.
- Tiles can move behind nginx/CDN/GitHub Pages with zero code change if the
  demo needs to survive the API being restarted.
- GDAL/PROJ problems are build-time problems with a readable log.
- `rasterio` stays out of `core/`'s dependency surface, preserving the purity
  rule from `docs/system-design.md` §2.

**Harder**
- `make seed` gets longer and produces ~150 MB. `.gitignore` must exclude
  `data/tiles/`, and the runbook must say tiles are generated, not committed.
- Restyling a layer is an offline re-render, not a query parameter.
- Two code paths exist (static hit, dynamic fallback), so the fallback needs a
  test or it will rot. Mitigated by keeping it to ~15 lines that call the same
  renderer the seed script does.

**To revisit**
- If the map gains deep zoom (z > 7) or a per-site DEM inset at 5 m, the pyramid
  stops being small and Option C becomes correct.
- If illumination ever becomes window-dependent (an "illumination during *this*
  mission window" layer is a genuinely good feature), that specific layer must
  become dynamic — it is parameterised by the slider and cannot be enumerated.
  That would be a per-layer decision, not a reversal of this one.

## Action Items
1. [ ] `data/ingest_lola.py`: fetch/clip the DEM to the polar extent, write a COG.
2. [ ] `data/render_tiles.py`: rio-tiler + morecantile pyramid for the three
       layers, z0–z5, skipping out-of-extent tiles.
3. [ ] `api/v1/routes/tiles.py`: static hit → 204 out-of-extent → dynamic
       write-through fallback; `ETag`, `immutable`, `X-Tile-Source`.
4. [ ] `.gitignore` `data/tiles/`; `make tiles` target; runbook entry.
5. [ ] Legend copy for `psr` stating the multi-year basis of the claim.
