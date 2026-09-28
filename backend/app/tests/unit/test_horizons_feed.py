"""JPL Horizons trajectories for the real orbiters (T1, F2): parser and products.

Fixtures fetched from the Horizons API on 2026-09-28: LRO over IM-2's surface
days (5-minute VECTORS), and CAPSTONE's answer for dates past its data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.feeds import targets
from app.feeds.adapters import horizons
from app.feeds.base import ParseError

FX = Path(__file__).resolve().parents[1] / "fixtures" / "feeds"


def test_vectors_become_moon_centred_states_in_si() -> None:
    p = horizons.parse((FX / "horizons_lro_im2.txt").read_bytes())
    v = p.values
    assert v["naif_id"] == -85 and v["source"] == "LRO_merged" and v["frame"] == "J2000"
    assert v["step_s"] == pytest.approx(300.0)
    et, x, y, z, vx, vy, vz = v["rows"][0]
    # 2025-03-06 16:00 TDB is 9196 days and 4 hours past J2000, read from the Julian date
    # (printed to 1e-9 day, so kept to the millisecond).
    assert et == pytest.approx(794_548_800.0, abs=1e-3)
    r = (x * x + y * y + z * z) ** 0.5
    assert 1_780e3 < r < 1_900e3  # LRO: 50-160 km above the Moon
    assert 1_400.0 < (vx * vx + vy * vy + vz * vz) ** 0.5 < 1_800.0
    assert len(v["rows"]) == 16 * 12 + 1
    assert p.valid_from == datetime(2025, 3, 6, 15, 58, 50, 816000, tzinfo=UTC)


def test_no_trajectory_for_the_dates_is_an_answer_not_a_failure() -> None:
    p = horizons.parse((FX / "horizons_capstone_after_end.txt").read_bytes())
    assert p.values["rows"] == [] and "after A.D. 2026-AUG-14" in p.values["no_data"]
    assert p.valid_from == p.valid_to == datetime(2026, 8, 14, 11, 58, tzinfo=UTC)


def test_other_bodies_are_refused() -> None:
    with pytest.raises(ParseError):
        horizons.parse(b"<html>busy</html>")
    body = (FX / "horizons_lro_im2.txt").read_bytes().replace(b"Moon (301)", b"Earth (399)")
    with pytest.raises(ParseError, match="not centred on the Moon"):
        horizons.parse(body)


def test_products_roll_weekly_and_keep_each_flown_mission_once() -> None:
    now = datetime(2026, 9, 28, 13, 5, tzinfo=UTC)
    ps = horizons.products(
        [("lro", -85)],
        [
            (
                "im-2",
                datetime(2025, 3, 6, 17, 30, tzinfo=UTC),
                datetime(2025, 3, 7, 6, 15, tzinfo=UTC),
            )
        ],
        now=lambda: now,
    )
    rolling, once = ps
    assert rolling.location_key == "lro" and rolling.interval_s == 7 * 86400
    assert rolling.params["START_TIME"] == "'2026-09-21 00:00'"
    assert rolling.params["STOP_TIME"] == "'2026-10-28 00:00'"
    assert once.location_key == "lro@im-2"
    assert once.params["START_TIME"] == "'2025-03-06 16:00'"
    assert once.params["STOP_TIME"] == "'2025-03-07 08:00'"  # +2 h, from the hour
    assert not rolling.keep_raw


def test_the_orbiters_and_flown_missions_come_from_the_catalogues() -> None:
    assert ("lro", -85) in targets.orbiters() and len(targets.orbiters()) == 4
    days = {m for m, _s, _e in targets.flown_surface_days()}
    assert {"im-1", "im-2", "blue-ghost-m1"} <= days and "peregrine-m1" not in days
