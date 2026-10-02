"""The ``rover`` job (T1, F5): can the rover and the lander see each other.

Runs in the compute worker: it reads the landing spot's selected native
3/4/5 m window, else the 20 m or 80 m model, which the
API process never loads. Inputs: the mission record, its landing spot, the
rover, and the antenna heights and radio frequency (assumed unless given).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import numpy as np

from app.config import get_settings
from app.core import viewshed
from app.core.quantity import Quantity
from app.data import rover_terrain
from app.data.lola import DemTile, make_samplers
from app.db.repositories.jobs import InputRef
from app.db.repositories.missions import MissionRepository
from app.db.session import session_scope
from app.services import lifecycle
from app.workers.compute import HandlerResult, JobContext, handler

BEARING_STEP_DEG = 5.0
RANGE_CELLS = 20


def _pct(lo_hi: tuple[float, float] | None, what: str) -> dict[str, Any]:
    if lo_hi is None:
        return lifecycle.missing("%", "The elevation model covers none of the ground around it.")
    lo, hi = (100.0 * x for x in lo_hi)
    if hi - lo < 1e-9:
        return lifecycle.q(
            Quantity(
                value=lo,
                unit="%",
                provenance="computed",
                no_margin_reason=f"Every cell is surely {what} or surely not.",
            )
        )
    return lifecycle.q(
        Quantity(value=(lo + hi) / 2.0, unit="%", provenance="computed", lo=lo, hi=hi)
    )


def _assumed(value: float, unit: str, given: bool, why: str) -> dict[str, Any]:
    return lifecycle.q(
        Quantity(
            value=value,
            unit=unit,
            provenance="assumed",
            no_margin_reason="As given in the request." if given else why,
        )
    )


#: What the answer says about clear, blocked and uncertain. The radio path needs more than the
#: line of sight: the space around it that the signal needs (the first Fresnel zone).
RADIO_NOTE = (
    "Clear: the terrain stays below the line between the antennas by more than the terrain "
    "map’s height error; blocked: it rises above by more than that; uncertain: the map cannot "
    "tell. The radio path is clear only if the space around the line of sight that the radio "
    "signal needs is clear too. Ground within two map cells of either end is not counted as "
    "a blocker."
)


@handler("rover")
async def run(ctx: JobContext) -> HandlerResult:
    p = ctx.job.params
    t_wall = time.perf_counter()
    s = get_settings()
    async with session_scope() as sess:
        m = await MissionRepository(sess).get(p["mission_id"])
    if m is None:
        raise ValueError("the mission is gone")
    path = s.data_dir / p["terrain_file"]
    if rover_terrain.version(path) != p["terrain_version"]:
        raise ValueError("Rover terrain changed after this job was queued; request it again.")
    tile = DemTile.load(path)
    sample, sigma = make_samplers(p["lat_deg"], p["lon_deg"], tile)
    ctx.progress(0.3, "Elevation model read.")
    radius = float(p["radius_m"])
    ranges = radius * np.arange(1, RANGE_CELLS + 1) / RANGE_CELLS
    bearings = np.arange(0.0, 360.0, BEARING_STEP_DEG)
    v = viewshed.compute(
        sample,
        sigma,
        bearings_deg=bearings,
        ranges_m=ranges,
        lander_antenna_m=float(p["lander_antenna_m"]),
        rover_antenna_m=float(p["rover_antenna_m"]),
        frequency_hz=float(p["freq_mhz"]) * 1e6,
        post_m=tile.scale_m,
    )
    words = viewshed.STATE_WORDS
    rover = p["rover"]
    no_drive = (
        f"No drive is published for {rover['name']}, so no stretch of it can be measured; "
        "the share is over the ground around the lander instead."
    )
    data = {
        "rover": rover,
        "share_basis": "ground",
        "radius_m": radius,
        "viewshed": {
            "bearings_deg": [float(x) for x in bearings],
            "ranges_m": [float(x) for x in ranges],
            "sight": [[words[c] for c in row] for row in v.sight],
            "radio": [[words[c] for c in row] for row in v.radio],
        },
        "viewshed_tile": None,
        "out_of_sight_share": _pct(viewshed.ground_share(v, v.sight), "in sight"),
        "radio_not_clear_share": _pct(viewshed.ground_share(v, v.radio), "on a clear path"),
        "longest_out_of_sight_m": lifecycle.missing("m", no_drive),
        "resolvable": True,
        "reason": None,
        "assumptions": {
            "lander_antenna_m": _assumed(
                float(p["lander_antenna_m"]),
                "m",
                bool(p["given"]["lander_antenna_m"]),
                "The lander's antenna height is not published; assumed. Give lander_antenna_m.",
            ),
            "rover_antenna_m": _assumed(
                float(p["rover_antenna_m"]),
                "m",
                bool(p["given"]["rover_antenna_m"]),
                "The rover's antenna height is not published; assumed. Give rover_antenna_m.",
            ),
            "radio_mhz": _assumed(
                float(p["freq_mhz"]),
                "MHz",
                bool(p["given"]["freq_mhz"]),
                "The rover's radio frequency is not published; 2.4 GHz is assumed (only the "
                "radio path depends on it). Give freq_mhz.",
            ),
        },
        "terrain": {
            "product": tile.product,
            "post_m": tile.scale_m,
            "vertical_error_m": tile.vertical_error_m,
        },
        "note": RADIO_NOTE + " The finest available terrain covering the lander's ground "
        "and the whole requested neighbourhood is used. A gap at the lander or a window "
        "edge can require a coarser model; gaps along a ray remain uncertain.",
    }
    ms = (time.perf_counter() - t_wall) * 1000.0
    meta = lifecycle.meta(
        engines=("los",),
        sources=[
            lifecycle.source_ref(
                f"Lunar terrain map ({tile.product})",
                rover_terrain.STEREO_SOURCE
                if tile.product == rover_terrain.STEREO_PRODUCT
                else rover_terrain.NOBILE03_SOURCE
                if tile.product == rover_terrain.NOBILE03_PRODUCT
                else "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/",
            )
        ],
        parts=[
            (
                "Terrain height (lunar terrain map)",
                f"A cell is uncertain when the map’s height error ({tile.vertical_error_m:g} m "
                f"for cells {tile.scale_m:g} m wide) could tip it either way; the shares are "
                "ranges for that reason.",
            ),
            (
                "Antennas and radio",
                "Antenna heights and the frequency are assumed unless given; the line of "
                "sight depends on the heights, the radio path also on the frequency.",
            ),
        ],
        compute_ms=ms,
        computed_at=datetime.now(UTC),
    )
    return HandlerResult(
        result=lifecycle.jsonable({"data": data, "meta": meta}),
        inputs=[
            InputRef("mission", m.id, m.data_version),
            InputRef("terrain", p["site_id"], p["terrain_version"]),
        ],
        message="Line of sight worked out.",
    )
