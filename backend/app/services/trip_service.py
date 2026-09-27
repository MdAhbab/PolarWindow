"""Trip (T2): the flown trip from NASA's reconstruction, or why there is none yet.

A flown mission's trip is worked out once, as a job, from its reconstructed
trajectory in NAIF's CLPS SPICE archive. A mission that has not flown gets
a designed trip once its launch time is known (the launch calendar, D1/D2).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import engine_closure, get_settings
from app.data import catalogues, registry
from app.db.repositories.missions import MissionRepository
from app.services import job_service, lifecycle
from app.services.mission_service import MissionNotFound

KIND = "trip"
STEP_S = 60

#: Flown CLPS missions with a reconstructed trajectory: registry id and NAIF id.
FLOWN: dict[str, tuple[str, int]] = {
    "peregrine-m1": ("clps:peregrine_cruise", -244),
    "im-1": ("clps:im1_cruise", -370011),
    "blue-ghost-m1": ("clps:bgm1_cruise", -2711),
    "im-2": ("clps:im2_cruise", -370021),
}


def _none(reason: str) -> dict[str, Any]:
    missing = lifecycle.missing("h", reason)
    return {
        "data": {
            "source": "none",
            "none_reason": reason,
            "start": None,
            "end": None,
            "coverage_note": None,
            "samples": [],
            "shadow": [],
            "heard": [],
            "numbers": {
                "sunlight_h": missing,
                "heard_h": missing,
                "longest_shadow_h": missing,
                "longest_unheard_h": missing,
            },
            "burns": [],
            "burns_note": None,
            "moon_pull": None,
            "radiation": None,
        },
        "meta": lifecycle.meta(engines=("traj",), sources=[], parts=[("No trip", reason)]),
    }


async def trip(session: AsyncSession, mission_id: str) -> tuple[int, dict[str, Any]]:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    if m.status in ("cancelled", "reassigned"):
        return 200, _none("This delivery was cancelled.")
    if m.id not in FLOWN:
        return 200, _none(
            "No trip has been worked out: a designed trip needs a launch time, and the "
            "launch calendar for this mission is not worked out yet."
        )
    ds_id, naif = FLOWN[m.id]
    ds = next(d for d in registry.DATASETS if d.id == ds_id)
    path = get_settings().data_dir / ds.dest
    if not path.exists():
        return 200, _none(
            f"NASA's reconstructed trajectory ({ds.dest}) is not on this "
            "machine yet; it arrives with the data sync (polar-data sync)."
        )
    params = {
        "mission_id": m.id,
        "data_version": m.data_version,
        "spk": ds.dest,
        "dataset": ds.id,
        "naif_id": naif,
        "title": ds.title,
        "url": ds.source,
        "step_s": STEP_S,
        "stations": catalogues.load("ground_stations").version,
    }
    ans = await job_service.answer_or_enqueue(
        session, kind=KIND, closure=engine_closure("traj", "ecl"), params=params, mission_id=m.id
    )
    if ans.assessment is None:
        assert ans.job is not None
        return 202, ans.job
    return 200, ans.assessment.result
