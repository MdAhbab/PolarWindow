"""Seed candidate landing sites from named lunar south-polar features.

The honest problem this solves
------------------------------
A landing site is not a crater. Every well-known name near the south pole --
Shackleton, Haworth, Shoemaker, Faustini -- refers to a *crater*, and the IAU
coordinate for a crater is its **centre**, which is the permanently shadowed
floor: the worst possible landing site and the exact opposite of what a planner
wants. Sampling the LOLA DEM at those published centres returns -2767 m, -3316 m
and -3932 m respectively. Anything that lists a crater's catalogue coordinate as
a "landing site" is quietly describing a hole.

So site coordinates here are **derived, not asserted**. For each named feature
we take an anchor position for the feature (several have informal names and no
IAU centre) and search the DEM over a stated region around it (an annulus at
the rim radius for crater-rim sites; a disc for massifs, ridges and plateaus). Among the landable
posts (slope under the limit) in the highest tenth of that region, the one with
the most open sky wins. The procedure, the anchor and the search parameters are
all recorded on the site, so the number can be reproduced or disputed rather
than merely trusted.

This is not a claim to be an official candidate-site list. It is a defensible,
reproducible way to get fifteen physically real, distinguishable sites onto a
map -- which is what the product needs to demonstrate the comparison it is
about.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Literal

import numpy as np
import numpy.typing as npt
from scipy.ndimage import maximum_filter

from app.core.projections import R_MOON_M, geographic_to_polar, polar_to_geographic
from app.data.lola import DemTile

log = logging.getLogger(__name__)

FloatArray = npt.NDArray[np.float64]

#: Steeper than this and a lander does not set down. A generous bound -- real
#: CLPS slope constraints are tighter (often 10 deg) -- chosen so the search does
#: not fail on an 80 m DEM, whose posts smooth real slopes considerably.
MAX_LANDABLE_SLOPE_DEG: Final[float] = 12.0

#: How far the horizon proxy reaches; the search window is padded by this.
PROXY_REACH_M: Final[float] = 50_000.0

#: A site must be in the top (100 - this) per cent of elevation within its
#: own search region before openness is considered. 90 puts a rim site on the
#: crest rather than partway down the inner wall, which at 75 it sometimes was.
HIGH_GROUND_PERCENTILE: Final[float] = 90.0

#: Two resolved sites must be at least this far apart. Below ~5 km two polar
#: sites share most of their skyline, so comparing them compares noise.
MIN_SITE_SEPARATION_M: Final[float] = 5000.0

SOURCE_ATLAS: Final[str] = "LPI Lunar South Pole Atlas (feature names and anchors)"
SOURCE_ATLAS_URL: Final[str] = "https://www.lpi.usra.edu/lunar_resources/lunarsouthpole/"
SOURCE_DEM: Final[str] = "LOLA LDEM 80S (PDS Geosciences Node)"


@dataclass(frozen=True, slots=True)
class SiteSeed:
    """A named feature and how to find a landing point on it."""

    id: str
    code: str
    name: str
    region: str
    #: IAU feature centre, the anchor for the search. Never the site itself.
    anchor_lat_deg: float
    anchor_lon_deg: float
    search: Literal["rim", "massif"]
    #: For "rim": the annulus is [inner, outer] km from the anchor.
    #: For "massif": the disc is [0, outer] km.
    inner_km: float
    outer_km: float
    note: str
    #: Restrict the search to a compass sector of the annulus, centred on this
    #: bearing from the anchor. Two sites on opposite shoulders of the same
    #: crater are genuinely different sites with different skylines, and
    #: "the north-east rim of Nobile" is how a planner would name one.
    bearing_deg: float | None = None
    sector_deg: float = 120.0


# A "Slater plain" seed was tried and removed. Every anchor available for it
# put the whole search region inside a basin -- the best post in a 12 km disc
# was -2,552 m, i.e. a crater floor -- and a search for unclaimed flat high
# ground within 90 km of the pole returned nothing. Rather than move the anchor
# until the number looked acceptable, the site is simply absent. Fifteen real
# sites is worth more than sixteen with one in a hole.

#: Fifteen sites spanning -84.3 to -89.9 deg. The latitude spread is the point:
#: within a degree of the pole the Sun never really sets and terrain alone
#: decides power, while by -85 deg the season reaches the site and no ridge is
#: responsible for the night. A set clustered at one latitude would make the
#: product look like it only has one answer.
SEEDS: Final[tuple[SiteSeed, ...]] = (
    SiteSeed(
        id="shackleton-rim",
        code="A",
        name="Shackleton rim, east shoulder",
        region="shackleton",
        anchor_lat_deg=-89.66,
        anchor_lon_deg=129.20,
        search="rim",
        inner_km=8.0,
        outer_km=12.0,
        bearing_deg=90.0,
        sector_deg=140.0,
        note="Almost exactly on the pole. Power is limited by terrain, not by the season.",
    ),
    SiteSeed(
        id="connecting-ridge",
        code="B",
        name="Connecting Ridge",
        region="shackleton",
        anchor_lat_deg=-89.45,
        anchor_lon_deg=222.0,
        search="massif",
        inner_km=0.0,
        outer_km=8.0,
        note="The saddle between Shackleton and de Gerlache. High, and unusually open.",
    ),
    SiteSeed(
        id="peak-near-shackleton",
        code="C",
        name="Peak near Shackleton",
        region="shackleton",
        anchor_lat_deg=-89.78,
        anchor_lon_deg=204.0,
        search="massif",
        inner_km=0.0,
        outer_km=7.0,
        note="A high point that holds sunlight when the surrounding rim does not.",
    ),
    SiteSeed(
        id="de-gerlache-rim",
        code="D",
        name="de Gerlache rim",
        region="de-gerlache",
        anchor_lat_deg=-88.50,
        anchor_lon_deg=272.90,
        search="rim",
        inner_km=13.0,
        outer_km=20.0,
        note="High and open. Little nearby stands more than a couple of degrees above level.",
    ),
    SiteSeed(
        id="de-gerlache-kocher-massif",
        code="E",
        name="de Gerlache-Kocher massif",
        region="de-gerlache",
        anchor_lat_deg=-88.10,
        anchor_lon_deg=291.0,
        search="massif",
        inner_km=0.0,
        outer_km=12.0,
        note="A massif between two craters, with a long view in most directions.",
    ),
    SiteSeed(
        id="haworth-rim",
        code="F",
        name="Haworth rim, north wall",
        region="haworth",
        anchor_lat_deg=-87.45,
        anchor_lon_deg=355.0,
        search="rim",
        inner_km=20.0,
        outer_km=28.0,
        bearing_deg=0.0,
        sector_deg=120.0,
        note="On the wall above a permanently shadowed floor. Close to ice, and it costs.",
    ),
    SiteSeed(
        id="malapert-massif",
        code="G",
        name="Malapert massif",
        region="malapert",
        anchor_lat_deg=-86.00,
        anchor_lon_deg=2.70,
        search="massif",
        inner_km=0.0,
        outer_km=15.0,
        note="Superb view of Earth, and far enough from the pole to have a real night.",
    ),
    SiteSeed(
        id="shoemaker-rim",
        code="H",
        name="Shoemaker rim",
        region="shoemaker",
        anchor_lat_deg=-88.10,
        anchor_lon_deg=44.90,
        search="rim",
        inner_km=22.0,
        outer_km=30.0,
        bearing_deg=200.0,
        sector_deg=120.0,
        note="A compromise site: nothing outstanding, nothing disqualifying.",
    ),
    SiteSeed(
        id="faustini-rim",
        code="I",
        name="Faustini rim",
        region="faustini",
        anchor_lat_deg=-87.30,
        anchor_lon_deg=77.00,
        search="rim",
        inner_km=16.0,
        outer_km=22.0,
        note="Rim of a large cold trap, one of the most-studied ice targets.",
    ),
    SiteSeed(
        id="nobile-rim-1",
        code="J",
        name="Nobile rim 1",
        region="nobile",
        anchor_lat_deg=-85.20,
        anchor_lon_deg=53.50,
        search="rim",
        inner_km=28.0,
        outer_km=36.0,
        bearing_deg=45.0,
        sector_deg=90.0,
        note="Furthest from the pole in this set, so the seasons reach it.",
    ),
    SiteSeed(
        id="nobile-rim-2",
        code="K",
        name="Nobile rim 2",
        region="nobile",
        anchor_lat_deg=-85.40,
        anchor_lon_deg=33.00,
        search="rim",
        inner_km=28.0,
        outer_km=36.0,
        bearing_deg=225.0,
        sector_deg=90.0,
        note="The opposite shoulder of Nobile, with a different skyline entirely.",
    ),
    SiteSeed(
        id="amundsen-rim",
        code="L",
        name="Amundsen rim",
        region="amundsen",
        anchor_lat_deg=-84.50,
        anchor_lon_deg=82.80,
        search="rim",
        inner_km=44.0,
        outer_km=54.0,
        bearing_deg=180.0,
        sector_deg=120.0,
        note="A large, old crater well away from the pole. Long days and long nights.",
    ),
    SiteSeed(
        id="leibnitz-beta-plateau",
        code="M",
        name="Leibnitz Beta plateau",
        region="leibnitz",
        anchor_lat_deg=-85.30,
        anchor_lon_deg=32.50,
        search="massif",
        inner_km=0.0,
        outer_km=12.0,
        note="A broad high plateau rather than a rim: flatter, and less sheltered.",
    ),
    SiteSeed(
        id="sverdrup-rim",
        code="N",
        name="Sverdrup rim",
        region="sverdrup",
        anchor_lat_deg=-88.30,
        anchor_lon_deg=207.40,
        search="rim",
        inner_km=14.0,
        outer_km=22.0,
        note="Near-polar, and shadowed from a different direction than Shackleton.",
    ),
    SiteSeed(
        id="cabeus-rim",
        code="O",
        name="Cabeus rim",
        region="cabeus",
        anchor_lat_deg=-85.30,
        anchor_lon_deg=317.90,
        search="rim",
        inner_km=42.0,
        outer_km=52.0,
        bearing_deg=180.0,
        sector_deg=120.0,
        note="Rim of the LCROSS impact crater. The best-characterised volatiles in the region.",
    ),
)


@dataclass(frozen=True, slots=True)
class ResolvedSite:
    """A seed turned into real coordinates by searching the DEM."""

    id: str
    code: str
    name: str
    region: str
    lat_deg: float
    lon_deg: float
    elev_m: float
    slope_deg: float
    note: str
    anchor_lat_deg: float
    anchor_lon_deg: float
    search_kind: str
    search_inner_km: float
    search_outer_km: float
    offset_from_anchor_km: float
    source: str
    source_url: str
    source_note: str


def _slope_deg(heights: npt.NDArray[np.float32], scale_m: float) -> FloatArray:
    """Local slope magnitude in degrees, from a central-difference gradient."""
    gy, gx = np.gradient(heights.astype(np.float64), scale_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    return np.asarray(slope, dtype=np.float64)


def _horizon_proxy_deg(
    heights: npt.NDArray[np.float32],
    scale_m: float,
    radii_m: tuple[float, ...] = (
        400.0,
        1000.0,
        2500.0,
        6000.0,
        12000.0,
        25000.0,
        50000.0,
    ),
    r_body_m: float = R_MOON_M,
) -> FloatArray:
    """Approximate skyline elevation angle for every post, degrees.

    A whole-grid, ring-based approximation of the ray-march in
    ``core/horizon.py``: for each radius, ``maximum_filter`` gives the highest
    terrain within that distance, which bounds the skyline at that scale. The
    lunar curvature drop is subtracted exactly as in the real mask, which is
    what stops distant high ground from dominating -- at 12 km the drop is 41 m,
    at 25 km it is 180 m.

    It is an upper bound rather than the true horizon, because a maximum within
    a disc may sit in a different direction than the one being tested. That is
    acceptable here: it is used to *rank* candidate posts within one small
    region, where the bias is common to all of them, and the real 1440-ray mask
    is computed properly afterwards for whichever post wins.

    The radii run out to 50 km for a specific reason. Shoemaker is 51 km across,
    Nobile 73 km and Cabeus 98 km; a proxy that only reached 12 km would see
    nothing above a post standing on the floor of any of them and would score
    that floor as beautifully open sky. It is open, in the sense that the rim is
    far away -- and it is also permanently dark, because at the pole the Sun sits
    at roughly zero elevation and even a distant rim is above it.
    """
    h = heights.astype(np.float64)
    worst = np.full(h.shape, -90.0, dtype=np.float64)
    for r in radii_m:
        size = max(3, int(round(2.0 * r / scale_m)) | 1)
        local_max = maximum_filter(h, size=size, mode="nearest")
        drop = r * r / (2.0 * r_body_m)
        theta = np.degrees(np.arctan2(local_max - h - drop, r))
        worst = np.maximum(worst, theta)
    return np.asarray(worst, dtype=np.float64)


def resolve(
    seed: SiteSeed,
    tile: DemTile,
    *,
    max_slope_deg: float = MAX_LANDABLE_SLOPE_DEG,
    exclude: list[tuple[float, float]] | None = None,
) -> ResolvedSite:
    """Find a landing point for one seed by searching the DEM.

    Selection rule, stated plainly so it can be argued with: **among the posts
    in the search region whose local slope is under the threshold and whose
    height is in the region's top decile, the one with the most open sky**
    (the lowest coarse horizon, from the ring proxy in `_horizon_proxy_deg`).

    Openness is the criterion because it is directly what the four key numbers
    reward. The high-ground floor stops a large crater's floor from scoring as
    "open" while sitting in permanent shadow. Slope is a hard filter rather than
    a weighted term because a steep spot is not a worse site, it is not a site.
    The two rules tried before this one, and why each failed, are recorded
    beside the scoring code below.
    """
    ax, ay = geographic_to_polar(np.array([seed.anchor_lon_deg]), np.array([seed.anchor_lat_deg]))
    ax_f, ay_f = float(ax[0]), float(ay[0])

    outer_m = seed.outer_km * 1000.0
    inner_m = seed.inner_km * 1000.0

    # Window of the regional tile covering the search region, padded by the
    # proxy's reach so the maximum filters see real terrain rather than the
    # edge-replicated values that `mode='nearest'` would invent.
    half_px = int(np.ceil((outer_m + PROXY_REACH_M) / tile.scale_m)) + 2
    c0 = int(round((ax_f - tile.origin_x_m) / tile.scale_m))
    r0 = int(round((tile.origin_y_m - ay_f) / tile.scale_m))
    h, w = tile.heights.shape
    cs, ce = max(0, c0 - half_px), min(w, c0 + half_px + 1)
    rs, re = max(0, r0 - half_px), min(h, r0 + half_px + 1)
    if ce <= cs or re <= rs:
        raise ValueError(f"{seed.id}: anchor falls outside the regional DEM")

    sub = tile.heights[rs:re, cs:ce]
    slope = _slope_deg(sub, tile.scale_m)

    cols = np.arange(cs, ce)
    rows = np.arange(rs, re)
    gx = tile.origin_x_m + cols * tile.scale_m
    gy = tile.origin_y_m - rows * tile.scale_m
    gxx, gyy = np.meshgrid(gx, gy)
    dist = np.hypot(gxx - ax_f, gyy - ay_f)

    in_region = (dist >= inner_m) & (dist <= outer_m)

    if seed.bearing_deg is not None:
        # Bearing of each post from the anchor, in true-north-clockwise terms.
        # Grid north is not true north near the pole, but the anchor and the
        # post are close enough together that the convergence is common to both
        # and cancels; using grid bearing here is correct to well under a degree
        # and this is a coarse sector filter, not a measurement.
        brg = np.degrees(np.arctan2(gxx - ax_f, gyy - ay_f)) % 360.0
        delta = np.abs((brg - seed.bearing_deg + 180.0) % 360.0 - 180.0)
        in_region &= delta <= seed.sector_deg / 2.0

    landable = slope <= max_slope_deg
    valid = in_region & landable & np.isfinite(sub)

    if not valid.any():
        # Relax the slope filter rather than fail: report the real slope so the
        # site is visibly marginal instead of silently excluded.
        valid = in_region & np.isfinite(sub)
        if not valid.any():
            raise ValueError(f"{seed.id}: no DEM coverage in the search region")
        log.warning(
            "%s: no point under %.0f deg slope; taking the best available", seed.id, max_slope_deg
        )

    if exclude:
        # Keep sites distinct. Two "sites" at the same post are one site with
        # two names, and a comparison tool whose rows are secretly the same
        # place is worse than useless.
        for ex_x, ex_y in exclude:
            valid &= np.hypot(gxx - ex_x, gyy - ex_y) >= MIN_SITE_SEPARATION_M
        if not valid.any():
            raise ValueError(
                f"{seed.id}: every landable point in the search region is within "
                f"{MIN_SITE_SEPARATION_M / 1000:.0f} km of an already-placed site"
            )

    # Score by how OPEN the local sky is -- directly the quantity this whole
    # product exists to report.
    #
    # Two earlier rules were tried and both failed on real data, which is worth
    # recording because the failures are instructive:
    #
    #   * "highest post in the region" wandered off to whatever distant massif
    #     clipped the annulus. It put both Nobile sites on the same 7 km peak
    #     40 km away -- the global maximum of the entire DEM, and not on
    #     Nobile's rim at all.
    #   * "most locally prominent post" fixed that but ignores absolute height,
    #     so a one-metre bump on a crater floor outscored the Malapert summit.
    #     It moved Malapert off a 5,172 m, 0.8-degree summit onto a 3,440 m,
    #     11.8-degree slope.
    #
    # What both proxies were groping at is the real criterion: a good polar site
    # is one where terrain does not stand between you and the Sun. That is the
    # horizon mask, and a coarse version of it is cheap to evaluate for every
    # post at once. For each of a few ring radii, the maximum terrain height
    # within that radius sets an upper bound on the skyline at that scale:
    #
    #     theta(r) = atan((max_h_within_r - h_here - r^2/2R) / r)
    #
    # and the site's openness is the worst (largest) theta over all radii,
    # negated so that more open is better. This is the same physics as
    # core/horizon.py, evaluated on 80 m posts over rings instead of 1440 rays,
    # and it selects for exactly what the four key numbers reward.
    openness = -_horizon_proxy_deg(sub, tile.scale_m)

    # A site must also be on the high ground of its own region.
    #
    # Openness alone is satisfied by the floor of a large crater: Cabeus is
    # 98 km across, so a post at its centre has nothing within 25 km taller than
    # it and scores as beautifully clear sky. It is clear, and it is also
    # permanently dark, because at the pole the Sun sits near zero elevation and
    # even a distant rim is above it.
    #
    # A local-prominence floor was tried first and is too weak: a metre-high
    # rise on a gently tilted crater floor has positive prominence. An elevation
    # percentile is cruder and much harder to fool -- it asks "is this among the
    # high ground *here*", which is the question, and it adapts to each region
    # without needing a per-region height threshold.
    candidate_h = sub.astype(np.float64)[valid]
    if candidate_h.size:
        cutoff = float(np.percentile(candidate_h, HIGH_GROUND_PERCENTILE))
        high_ground = sub.astype(np.float64) >= cutoff
        if (valid & high_ground).any():
            valid = valid & high_ground

    scores = np.asarray(np.where(valid, openness, -np.inf), dtype=np.float64)
    k = int(np.argmax(scores))
    ri, ci = np.unravel_index(k, scores.shape)

    x_best = float(gxx[ri, ci])
    y_best = float(gyy[ri, ci])
    lon, lat = polar_to_geographic(np.array([x_best]), np.array([y_best]))

    return ResolvedSite(
        id=seed.id,
        code=seed.code,
        name=seed.name,
        region=seed.region,
        lat_deg=round(float(lat[0]), 5),
        lon_deg=round(float(np.mod(lon[0], 360.0)), 5),
        elev_m=round(float(sub[ri, ci]), 1),
        slope_deg=round(float(slope[ri, ci]), 2),
        note=seed.note,
        anchor_lat_deg=seed.anchor_lat_deg,
        anchor_lon_deg=seed.anchor_lon_deg,
        search_kind=seed.search,
        search_inner_km=seed.inner_km,
        search_outer_km=seed.outer_km,
        offset_from_anchor_km=round(float(dist[ri, ci]) / 1000.0, 2),
        source=SOURCE_ATLAS,
        source_url=SOURCE_ATLAS_URL,
        source_note=(
            f"Derived, not catalogued. {anchor_words(seed)} "
            f"at {seed.anchor_lat_deg:.2f} deg, {seed.anchor_lon_deg:.2f} deg E. "
            f"The landing point is the post with the most open sky (lowest coarse "
            f"horizon) among those with local slope <= {max_slope_deg:.0f} deg and height "
            f"in the top {100 - HIGH_GROUND_PERCENTILE:.0f}% of a "
            f"{'ring' if seed.search == 'rim' else 'disc'} of "
            f"{seed.inner_km:.0f}-{seed.outer_km:.0f} km around that anchor, measured on "
            f"{SOURCE_DEM} at {tile.scale_m:.0f} m posts. Not a surveyed landing "
            f"ellipse and not an official candidate site."
        ),
    )


def anchor_words(seed: SiteSeed) -> str:
    """What the anchor is, and nothing more.

    The note used to call every anchor "the IAU centre of" its feature. Some
    features, Connecting Ridge among them, have informal names and no IAU
    centre, and the two Nobile rim sites search around two different anchors,
    which cannot both be the crater's centre. So the note says only that this
    is the point the search was centred on.
    """
    return f"The search was centred on {seed.name.split(',')[0]}"


def resolve_all(tile: DemTile) -> list[ResolvedSite]:
    """Resolve every seed, keeping the results mutually distinct.

    Sequential rather than independent, because each site excludes the ground
    already claimed by the ones before it. Order therefore matters and is the
    declaration order in SEEDS, which runs pole-outward -- the near-polar sites
    are the scarce, contested ground and get first claim.
    """
    out: list[ResolvedSite] = []
    claimed: list[tuple[float, float]] = []
    for seed in SEEDS:
        try:
            site = resolve(seed, tile, exclude=claimed)
        except ValueError as exc:
            log.error("skipping %s: %s", seed.id, exc)
            continue
        out.append(site)
        x, y = geographic_to_polar(np.array([site.lon_deg]), np.array([site.lat_deg]))
        claimed.append((float(x[0]), float(y[0])))
    return out


def main(dem_path: Path, out_path: Path) -> None:
    import json

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    tile = DemTile.load(dem_path)
    sites = resolve_all(tile)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([asdict(s) for s in sites], indent=2) + "\n", encoding="utf-8")
    log.info("wrote %d sites to %s", len(sites), out_path)
    log.info("")
    log.info("%-28s %9s %9s %8s %7s %8s", "site", "lat", "lon", "elev_m", "slope", "off_km")
    for s in sites:
        log.info(
            "%-28s %9.4f %9.4f %8.0f %7.1f %8.1f",
            s.id,
            s.lat_deg,
            s.lon_deg,
            s.elev_m,
            s.slope_deg,
            s.offset_from_anchor_km,
        )


if __name__ == "__main__":
    import sys

    main(Path(sys.argv[1]), Path(sys.argv[2]))
