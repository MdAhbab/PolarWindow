"""What the Contact answer says of each real orbiter's recorded trajectory: only what is that
orbiter's own, in plain words, and the section's note says the rest once."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.api.v1.schemas.contact import Node, Orbiter
from app.services import contact_service, lifecycle
from app.workers.handlers import orbiter_passes


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


#: What the feeds hold on 30 September 2026: CAPSTONE's Horizons trajectory ended on
#: 14 August (a snapshot that starts and ends there says "nothing after"), Chandrayaan-2's ends on
#: 23 October, LRO's and Danuri's run to the end of the 30 days the feeds ask for.
SPANS: dict[str, tuple[datetime, datetime]] = {
    "capstone": (_at("2026-08-14T00:00:00"), _at("2026-08-14T00:00:00")),
    "chandrayaan-2-orbiter": (_at("2026-09-23T00:00:00"), _at("2026-10-23T04:58:50")),
    "lro": (_at("2026-09-23T00:00:00"), _at("2026-10-30T00:00:00")),
}


class _Feeds:
    def __init__(self, _session: Any) -> None:
        pass

    async def latest_ok_span(
        self, _provider: str, _product: str, key: str = ""
    ) -> tuple[int, datetime, datetime, datetime] | None:
        got = SPANS.get(key)
        return None if got is None else (7, got[0], got[1], _at("2026-09-30T00:00:00"))


def _orbiters(start: str, end: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    monkeypatch.setattr(contact_service, "FeedRepository", _Feeds)
    got = asyncio.run(contact_service._orbiters(None, "im-3", _at(start), _at(end)))  # type: ignore[arg-type]
    return {o["id"]: o for o in got}


def test_capstone_says_horizons_has_nothing_after_the_day_its_trajectory_ended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by = _orbiters("2026-10-20T00:00:00", "2026-10-28T00:00:00", monkeypatch)
    capstone = by["capstone"]
    assert capstone["snapshot_id"] is None
    assert capstone["gap"] == "JPL Horizons has no trajectory for CAPSTONE after 2026-08-14."
    assert capstone["missing"] == (
        "No JPL Horizons trajectory is recorded for these dates. "
        "JPL Horizons has no trajectory for CAPSTONE after 2026-08-14."
    )


def test_chandrayaan_2_is_covered_to_the_day_its_trajectory_ends_and_lro_to_the_end_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by = _orbiters("2026-10-20T00:00:00", "2026-10-28T00:00:00", monkeypatch)
    assert by["chandrayaan-2-orbiter"]["snapshot_id"] == 7 and by["lro"]["snapshot_id"] == 7
    assert by["danuri"]["snapshot_id"] is None and by["danuri"]["gap"] is None
    assert by["danuri"]["missing"] == "No JPL Horizons trajectory is recorded for these dates yet."


def test_dates_after_everything_recorded_say_where_each_recorded_trajectory_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by = _orbiters("2026-11-02T00:00:00", "2026-11-05T00:00:00", monkeypatch)
    assert by["chandrayaan-2-orbiter"]["gap"] == (
        "The recorded JPL Horizons trajectory for Chandrayaan-2 orbiter ends 2026-10-23."
    )
    assert by["lro"]["gap"].endswith("ends 2026-10-30.")
    assert "(recorded: 2026-09-23 to 2026-10-23)" in by["chandrayaan-2-orbiter"]["missing"]
    # Dates before what is recorded say where it starts.
    early = _orbiters("2026-09-01T00:00:00", "2026-09-05T00:00:00", monkeypatch)
    assert early["lro"]["gap"] == (
        "The recorded JPL Horizons trajectory for Lunar Reconnaissance Orbiter starts 2026-09-23."
    )


def _passes(a: float, b: float) -> orbiter_passes.Passes:
    return orbiter_passes.Passes(runs=[], a=a, b=b, edge_tol_s=[], grazes=0, max_el_deg=[])


def test_an_orbiter_cut_short_says_where_and_one_that_covers_the_dates_says_nothing() -> None:
    start, day = _at("2026-10-20T00:00:00"), 86400.0
    whole = orbiter_passes.edges("Danuri", _passes(0.0, 8 * day), start, 8 * day)
    assert whole is None
    short = orbiter_passes.edges("Chandrayaan-2 orbiter", _passes(0.0, 3.2 * day), start, 8 * day)
    assert short == (
        "The recorded JPL Horizons trajectory for Chandrayaan-2 orbiter ends 2026-10-23. "
        "No pass after then is worked out."
    )
    late = orbiter_passes.edges("LRO", _passes(2 * day, 8 * day), start, 8 * day)
    assert late is not None and "starts 2026-10-22." in late and "before then" in late
    both = orbiter_passes.edges("LRO", _passes(day, 2 * day), start, 8 * day)
    assert both is not None and both.count("No pass") == 2


def test_no_orbiter_repeats_the_section_note() -> None:
    rec = type("Rec", (), {"id": "lro", "name": "LRO", "operator": "NASA", "naif_id": -85})()
    start = _at("2026-10-20T00:00:00")
    covered = orbiter_passes.block(rec, None, _passes(0.0, 86400.0), start, 86400.0, None)
    assert covered["note"] is None
    none = orbiter_passes.block(
        rec, None, None, start, 86400.0, "No JPL Horizons trajectory is recorded.", "The gap."
    )
    assert none["note"] == "The gap."
    for o in (covered, none):
        assert o["note"] != orbiter_passes.NOTE


def test_the_wire_shape_takes_a_note_or_none_and_a_relay_launched_but_not_operating() -> None:
    node = {
        "id": "x",
        "kind": "relay",
        "name": "X",
        "operator": None,
        "status": "launched_not_operating",
        "orbit": "real",
        "launch_note": None,
    }
    assert Node.model_validate(node).status == "launched_not_operating"
    assert Orbiter.model_fields["note"].annotation == (str | None)
    edge = lifecycle.trajectory_edge("X", _at("2026-10-23T04:58:50") + timedelta(0), ends=True)
    assert edge == "The recorded JPL Horizons trajectory for X ends 2026-10-23."
