"""The ``rover`` job (T1, F5): can the rover and the lander see each other.

Runs in the compute worker: it reads the landing spot's elevation windows
(the 20 m polar model around the site, else the 80 m regional one), which the
API process never loads. Inputs: the mission record, its landing spot, the
rover, and the antenna heights and radio frequency (assumed unless given).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import numpy as np

from app.config import ENGINE_VERSION, get_settings
from app.core import viewshed
from app.core.quantity import Quantity
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


@handler("rover")
async def run(ctx: JobContext) -> HandlerResult:
    p = ctx.job.params
    t_wall = time.perf_counter()
    s = get_settings()
    async with session_scope() as sess:
        m = await MissionRepository(sess).get(p["mission_id"])
    if m is None:
        raise ValueError("the mission is gone")
    fine_p = s.fine_dem_path(p["site_id"])
    fine = DemTile.load(fine_p) if fine_p.exists() else None
    coarse = None if fine is not None else DemTile.load(s.regional_dem_path)
    tile = fine if fine is not None else coarse
    assert tile is not None
    sample, sigma = make_samplers(p["lat_deg"], p["lon_deg"], fine, coarse)
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
        "note": "Clear: the terrain stays below the line between the antennas by more than "
        "the elevation model's height error; blocked: it rises above by more than that; "
        "uncertain: the model cannot tell. The radio path also needs the first Fresnel zone "
        "clear. Ground within two model posts of either end is not counted as a blocker.",
    }
    ms = (time.perf_counter() - t_wall) * 1000.0
    meta = lifecycle.meta(
        engines=("los",),
        sources=[
            lifecycle.source_ref(
                f"LOLA polar elevation model ({tile.product})",
                "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/",
            )
        ],
        parts=[
            (
                "Terrain height (LOLA polar model)",
                f"A cell is uncertain when the model's height error ({tile.vertical_error_m:g} m "
                f"at {tile.scale_m:g} m posts) could tip it either way; the shares are ranges "
                "for that reason.",
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
            InputRef("terrain", p["site_id"], f"{tile.product}@{ENGINE_VERSION}"),
        ],
        message="Line of sight worked out.",
    )
