"""Trip (T2): the flown trip from NASA's reconstruction, or why there is none yet.

A flown mission's trip is worked out once, as a job, from its reconstructed
trajectory in NAIF's CLPS SPICE archive. A mission that has not flown gets
a designed trip once its launch time is known (the launch calendar, D1/D2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import engine_closure, get_settings
from app.core import oem, spice
from app.data import catalogues, registry
from app.db.repositories.missions import MissionRepository
from app.services import ascent, job_service, launch_service, lifecycle
from app.services.mission_service import MissionNotFound

KIND = "trip"
STEP_S = 60

#: Flown CLPS missions with a reconstructed trajectory: registry id and NAIF id.
FLOWN = ascent.RECONSTRUCTED


def _none(reason: str) -> dict[str, Any]:
    missing = lifecycle.missing("h", reason)
    return {
        "data": {
            "source": "none",
            "none_reason": reason,
            "start": None,
            "end": None,
            "coverage_note": None,
            "covered": [],
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
            "corrections": None,
            "corrections_note": reason,
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
    flights, _ = await launch_service.reconstructed_flights(session)
    params = {
        "mission_id": m.id,
        "flights": flights,
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


class NoExport(LookupError):
    """There is no trajectory to export for this mission; the message says why."""


EXPORT_STEP_S = 600.0


async def export(session: AsyncSession, mission_id: str, fmt: str) -> tuple[str, str, str]:
    """``(text, media type, file extension)``: the flown trajectory as a CCSDS OEM or CSV.

    Earth-centred, SPICE ``J2000`` (EME2000), sampled every ten minutes from
    NASA's reconstruction, one block per stretch it covers.
    """
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    if m.id not in FLOWN:
        raise NoExport(
            "Only a flown trip can be exported for now: a designed trip is not worked out yet."
        )
    ds_id, naif = FLOWN[m.id]
    ds = next(d for d in registry.DATASETS if d.id == ds_id)
    path = get_settings().data_dir / ds.dest
    if not path.exists():
        raise NoExport(f"NASA's reconstructed trajectory ({ds.dest}) is not on this machine yet.")

    def build() -> list[oem.Segment]:
        spice.load_extra([path])
        segs = []
        for a, b in spice.coverage(path, naif):
            n = max(2, int((b - a) // EXPORT_STEP_S) + 1)
            ets = np.linspace(a, a + (n - 1) * EXPORT_STEP_S, n)
            if ets[-1] < b:
                ets = np.append(ets, b)
            st = spice.states(str(naif), "EARTH", spice.J2000, "NONE", ets)
            segs.append(oem.Segment([spice.et_to_utc(t)[:-1] for t in ets], st))
        return segs

    segs = await spice.run_async(build)
    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    frame_note = (
        f"{m.name}: NASA's reconstructed trajectory ({ds.title}), Earth-centred, "
        "SPICE J2000 (EME2000), km and km/s, every 10 minutes; "
        "each stretch NASA's reconstruction covers is numbered."
    )
    if fmt == "csv":
        return oem.csv_text(segs, frame_note), "text/csv", "csv"
    text = oem.oem(
        object_name=m.name,
        object_id=f"NAIF {naif}",
        center="EARTH",
        frame="EME2000",
        segments=segs,
        created=created,
        originator="POLAR WINDOW",
        comments=[
            f"Source: {ds.source}",
            "Sampled from the SPK every 600 s; SPICE J2000 is used as EME2000.",
            "One segment per stretch NASA's reconstruction covers; "
            "nothing is filled in across gaps.",
        ],
    )
    return text, "text/plain", "oem"
