"""Ask's tools (O1): durations in hours with their margins and in words, names beside
ids, and the open scenario read back with each value's label. No database, no model:
the services the tools call are replaced by canned payloads shaped like the real ones
(Connecting Ridge, 14 Mar to 12 Apr 2027, as the API returns them)."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from app.agents import chatter, guards, tools
from app.services import (
    compare_service,
    mission_service,
    sections_service,
    site_service,
    space_weather_service,
)

#: A field name or any other snake_case word: never in words a person reads.
SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")

AUTONOMY = {
    "worst_compound_s": 138206.216,
    "required_autonomy_s": 165847.459,
    "margin_fraction": 0.2,
    "survival_needed_s": 437647.796,
    "compound_inside_dark": True,
    "survival_open": False,
    "worst_compound_open": False,
}
#: `site_service.metrics_payload` for Connecting Ridge over the reference dates.
METRICS = {
    "site_id": "connecting-ridge",
    "start": "2027-03-14T00:00:00Z",
    "end": "2027-04-12T12:45:00Z",
    "sunlit_s": 2067837.726,
    "earth_contact_s": 1549023.017,
    "longest_dark_s": 437647.796,
    "longest_blackout_s": 1002476.983,
    "sun_fraction_up": 0.81044,
    "earth_fraction_up": 0.607103,
    "worst_compound_s": 138206.216,
    "longest_dark_open": False,
    "longest_blackout_open": False,
    "worst_compound_open": False,
    "sunlit_full_disc_s": 2000000.0,
    "sunlit_any_limb_s": 2100000.0,
    "earth_contact_full_disc_s": 1500000.0,
    "earth_contact_any_limb_s": 1600000.0,
    "sunlit_tolerance_s": 61527.5,
    "earth_contact_tolerance_s": 19080.0,
    "longest_dark_tolerance_s": 61527.5,
    "longest_blackout_tolerance_s": 19080.0,
    "longest_dark_grazing": False,
    "longest_blackout_grazing": False,
    "autonomy": AUTONOMY,
    "meta": {
        "uncertainty": {
            "edge_timing_s": 61527.5,
            "grazing": False,
            "coverage": 1.0,
            "terrain_modelled": True,
        }
    },
}
#: The same numbers at Malapert massif, whose longest night the dates cut short.
MALAPERT = {
    **METRICS,
    "site_id": "malapert-massif",
    "sunlit_s": 1418400.0,
    "sun_fraction_up": 0.556,
    "longest_dark_s": 1036800.0,
    "longest_dark_open": True,
    "longest_dark_tolerance_s": 25920.0,
    "worst_compound_s": 0.0,
    "autonomy": {**AUTONOMY, "worst_compound_s": 0.0, "required_autonomy_s": 0.0},
}


def _arc(up: bool, start: str, end: str, dur: float, tol: float, **kw: Any) -> dict[str, Any]:
    return {
        "up": up,
        "start": start,
        "end": end,
        "duration_s": dur,
        "tolerance_s": tol,
        "start_tolerance_s": tol / 2,
        "end_tolerance_s": tol / 2,
        "grazing": False,
        "open_start": False,
        "open_end": False,
        "blocked_by_bearing_deg": 212.5,
        "blocked_by_el_deg": 1.2,
        **kw,
    }


def _body(arcs: list[dict[str, Any]]) -> dict[str, Any]:
    up = sum(a["duration_s"] for a in arcs if a["up"])
    down = sum(a["duration_s"] for a in arcs if not a["up"])
    longest = max((a for a in arcs if not a["up"]), key=lambda a: a["duration_s"])
    return {
        "body": "x",
        "arcs": arcs,
        "up_s": up,
        "down_s": down,
        "fraction_up": round(up / (up + down), 6),
        "longest_down_s": longest["duration_s"],
        "longest_down_tolerance_s": longest["tolerance_s"],
        "longest_down_open": False,
        "grazing": False,
    }


#: `site_service.windows_payload`, cut to a few stretches.
WINDOWS = {
    "site_id": "connecting-ridge",
    "start": "2027-03-14T00:00:00Z",
    "end": "2027-04-12T12:45:00Z",
    "sun": _body(
        [
            _arc(
                True, "2027-03-14T00:00:00Z", "2027-03-20T06:00:00Z", 540000.0, 0.0, open_start=True
            ),
            _arc(False, "2027-03-20T06:00:00Z", "2027-03-25T07:47:00Z", 437647.796, 61527.5),
            _arc(
                True,
                "2027-03-25T07:47:00Z",
                "2027-04-12T12:45:00Z",
                1527837.726,
                0.0,
                open_end=True,
            ),
        ]
    ),
    "earth": _body(
        [
            _arc(
                True, "2027-03-14T00:00:00Z", "2027-03-24T00:00:00Z", 864000.0, 0.0, open_start=True
            ),
            _arc(False, "2027-03-24T00:00:00Z", "2027-04-04T14:27:00Z", 1002476.983, 19080.0),
            _arc(
                True, "2027-04-04T14:27:00Z", "2027-04-12T12:45:00Z", 685023.017, 0.0, open_end=True
            ),
        ]
    ),
    "compound": [
        {
            "start": "2027-03-24T00:00:00Z",
            "end": "2027-03-25T14:23:26Z",
            "duration_s": 138206.216,
            "open_start": False,
            "open_end": False,
        }
    ],
    "worst_compound_s": 138206.216,
    "meta": {},
}

SITES = {
    "connecting-ridge": "Connecting Ridge",
    "malapert-massif": "Malapert massif",
    "feature-reiner-gamma": "Reiner Gamma",
}


def _site(site_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=site_id,
        name=SITES[site_id],
        region="south pole",
        lat_deg=-89.45,
        lon_deg=-137.31,
        elev_m=1912.0,
        slope_deg=4.2,
        note=None,
        source_note=None,
        kind="candidate",
        terrain_modelled=True,
    )


def _mission(mid: str, name: str, status: str, site_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=mid,
        name=name,
        provider="Intuitive Machines",
        lander="Nova-C",
        status=status,
        site_id=site_id,
        launch=None,
        landing=None,
    )


MISSIONS = [
    _mission("im-2", "IM-2", "partial_success", "connecting-ridge"),
    _mission("im-3", "IM-3", "planned", "feature-reiner-gamma"),
]

#: A ready-made scenario of IM-3, as the scenario worker leaves its row.
SCENARIO = SimpleNamespace(
    id="sc-6e203e416683",
    mission_id="im-3",
    key="k",
    name="Defaults from past flights: Falcon 9 Block 5 from Launch Complex 39A",
    prompt=None,
    sections=["launch", "trip", "landing", "contact", "return"],
    preset=True,
    status="done",
    message="Worked out, except trip, which could not be.",
    assumptions=[
        {
            "field": "vehicle_id",
            "label": "Launch vehicle",
            "value": "falcon-9-b5",
            "display": "Falcon 9 Block 5",
            "unit": None,
            "basis": "default",
            "source": {"name": "Precedent: IM-2", "url": None, "fetched_at": None},
            "note": "IM-2 launched on this vehicle.",
        },
        {
            "field": "surface_days",
            "label": "Days on the surface",
            "value": 15.0,
            "display": "15 days",
            "unit": "days",
            "basis": "you",
            "source": None,
            "note": None,
        },
        {
            "field": "site_id",
            "label": "Landing spot",
            "value": "feature-reiner-gamma",
            "display": "Reiner Gamma",
            "unit": None,
            "basis": "published",
            "source": {"name": "NASA CLPS page", "url": None, "fetched_at": None},
            "note": None,
        },
    ],
    phases=[
        {"id": "inputs", "label": "Checking live sources", "state": "done", "detail": None},
        {"id": "launch", "label": "Launch", "state": "done", "detail": "Launch worked out."},
        {"id": "trip", "label": "Trip", "state": "failed", "detail": "No trip design converged."},
        {"id": "landing", "label": "Surface", "state": "done", "detail": None},
        {
            "id": "contact",
            "label": "Contact",
            "state": "skipped",
            "detail": "Needs a landing date.",
        },
        {"id": "return", "label": "Return", "state": "done", "detail": None},
    ],
    summaries={
        "launch": "12 launch opportunities from Launch Complex 39A between 2027-01-01 and "
        "2027-03-31."
    },
    results={
        "launch": {"data": {"opportunities": [{"id": "o1"}], "start": "2027-01-01"}},
        "landing": {
            "data": {
                "site_id": "feature-reiner-gamma",
                "site_name": "Reiner Gamma",
                "window_start": "2027-01-01T00:00:00Z",
                "window_end": "2027-01-16T00:00:00Z",
                "sunlit_s": 0.0,
                "earth_contact_s": 534658.577,
                "longest_dark_s": 1296000.0,
                "longest_blackout_s": 761341.423,
                "sun_fraction_up": 0.0,
                "earth_fraction_up": 0.412545,
                "longest_dark_open": True,
                "longest_blackout_open": True,
                "terrain_modelled": True,
            }
        },
    },
    created_by_name=None,
)

#: The contact step's answer, with one figure a tile can ask about.
CONTACT = {
    "data": {
        "heard_h": {"value": 120.4, "unit": "h", "pm": 0.3, "provenance": "computed"},
        "longest_message_wait_h": {
            "value": 6.2,
            "unit": "h",
            "pm": None,
            "provenance": "computed",
            "no_margin_reason": "Relay passes are timed to the minute.",
        },
    }
}
SECTIONS = {
    "data": [
        {"section": "ready", "state": "needs_input", "summary": ""},
        {"section": "launch", "state": "available", "summary": "12 launch opportunities"},
        {"section": "trip", "state": "no_data", "summary": ""},
        {"section": "contact", "state": "available", "summary": "Heard 120 hours"},
    ]
}
SPACE_WEATHER = {
    "data": {
        "now": {
            "kp": {"value": 2.7},
            "proton_10mev_pfu": {"value": 0.12},
            "xray_class": "B",
            "alerts": [],
        }
    }
}


class FakeMissions:
    def __init__(self, _session: Any) -> None:
        pass

    async def find(self, statuses: Any = None, q: Any = None) -> list[SimpleNamespace]:
        return list(MISSIONS)

    async def get(self, mid: str) -> SimpleNamespace | None:
        return next((m for m in MISSIONS if m.id == mid), None)


class FakeScenarios:
    """Reads only: a tool that tried to write would find no method to call."""

    calls: ClassVar[list[str]] = []

    def __init__(self, _session: Any) -> None:
        pass

    async def get(self, scenario_id: str) -> SimpleNamespace | None:
        FakeScenarios.calls.append(scenario_id)
        return SCENARIO if scenario_id == SCENARIO.id else None


def fake_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every service Ask's tools read, replaced by the canned payloads above."""

    async def cached_payload(_s: Any, kind: str, site_id: str, *_a: Any) -> dict[str, Any]:
        if kind == "windows":
            return {**WINDOWS, "site_id": site_id}
        return {"malapert-massif": MALAPERT}.get(site_id, {**METRICS, "site_id": site_id})

    async def require_site(_s: Any, site_id: str) -> SimpleNamespace:
        return _site(site_id)

    async def reference_summaries(_s: Any, ids: list[str]) -> dict[str, Any]:
        return {i: METRICS for i in ids}

    async def missions_for_sites(_s: Any, ids: list[str]) -> dict[str, Any]:
        return {i: [] for i in ids}

    async def list_with_summaries(_s: Any, **_kw: Any) -> SimpleNamespace:
        sites = [_site(i) for i in SITES]
        return SimpleNamespace(sites=sites, total=len(sites), summaries={})

    async def compare(
        _s: Any, ids: list[str], _start: Any, _end: Any, _step: Any, rank_by: str
    ) -> dict[str, Any]:
        def item(sid: str, rank: int | None, rr: list[int]) -> dict[str, Any]:
            m = MALAPERT if sid == "malapert-massif" else {**METRICS, "site_id": sid}
            return {
                "site_id": sid,
                "rank": rank,
                "rank_range": rr,
                "censored": rank is None,
                "incomparable_with": [],
                "metrics": m,
            }

        known = [s for s in ids if s in SITES]
        return {
            "rank_by": rank_by,
            "items": [item(s, 1, [1, 1]) for s in known[:1]]
            + [item(s, None, [1, len(known)]) for s in known[1:]],
            "ties": [known[:2]] if len(known) >= 2 else [],
            "unavailable": [
                {"site_id": s, "reason": "No terrain map covers it."} for s in ids if s not in SITES
            ],
        }

    async def sections(_s: Any, _mid: str) -> dict[str, Any]:
        return SECTIONS

    async def section(_s: Any, a: Any) -> dict[str, Any]:
        if a.section == "contact":
            return dict(CONTACT)
        return {"available": False, "reason": "Not yet."}

    async def now(_s: Any) -> dict[str, Any]:
        return SPACE_WEATHER

    monkeypatch.setattr(site_service, "cached_payload", cached_payload)
    monkeypatch.setattr(site_service, "require_site", require_site)
    monkeypatch.setattr(site_service, "reference_summaries", reference_summaries)
    monkeypatch.setattr(site_service, "list_with_summaries", list_with_summaries)
    monkeypatch.setattr(mission_service, "missions_for_sites", missions_for_sites)
    monkeypatch.setattr(compare_service, "compare", compare)
    monkeypatch.setattr(sections_service, "sections", sections)
    monkeypatch.setattr(space_weather_service, "now", now)
    monkeypatch.setattr(tools, "_section", section)
    monkeypatch.setattr(tools, "MissionRepository", FakeMissions)
    monkeypatch.setattr(tools, "ScenarioRepository", FakeScenarios)


async def run(name: str, args: dict[str, Any]) -> tools.ToolCallLog:
    return await tools.execute(None, name, args, 1)  # type: ignore[arg-type]


def grounded(text: str, *calls: tools.ToolCallLog) -> bool:
    return guards.check({"answer": text}, [c.as_dict() for c in calls]).ok


def phrases(words: dict[str, str]) -> str:
    return " ".join(words.values())


# ---------------------------------------------------------------------------
# Hours, margins and words
# ---------------------------------------------------------------------------


def test_the_four_numbers_come_in_hours_with_their_margins_and_in_words() -> None:
    fields, words = tools.in_hours(METRICS)
    assert fields["longest_dark_h"] == 121.6
    assert fields["longest_dark_tolerance_h"] == 17.1
    assert fields["sunlit_pct"] == 81.0
    assert words["Longest night"] == "122 h ± 17.1 h"
    assert words["Time in sunlight"] == "574 h ± 17.1 h, 81% of the time"
    assert words["Longest time without contact"] == "278 h ± 5.3 h"
    assert words["Time working alone"].startswith("46 h (no margin is worked out")
    assert "20% safety share" in words["Time working alone"]
    text = phrases(words)
    assert "second" not in text and not SNAKE.search(text)


def test_every_number_in_the_words_traces_to_the_tool_result() -> None:
    fields, words = tools.in_hours(METRICS)
    pool = tools.ToolCallLog(seq=1, tool="get_metrics", args={}, result={**METRICS, **fields})
    for phrase in words.values():
        assert grounded(phrase, pool), phrase


def test_a_small_margin_is_given_in_minutes_and_a_tiny_one_in_words() -> None:
    assert tools.margin_of(120.0, "longest_dark") == (
        {"longest_dark_tolerance_min": 2.0},
        "± 2 min",
    )
    assert tools.margin_of(20.0, "longest_dark") == ({}, "± under a minute")
    assert tools.margin_of(1800.0, "x") == ({"x_tolerance_h": 0.5}, "± 0.5 h")


def test_a_figure_without_a_margin_says_why() -> None:
    open_night = {**METRICS, "longest_dark_open": True}
    assert tools.in_hours(open_night)[1]["Longest night"] == (
        "at least 122 h ± 17.1 h, cut short by the dates"
    )
    grazing = {**METRICS, "longest_dark_grazing": True}
    assert "skims the skyline" in tools.in_hours(grazing)[1]["Longest night"]
    no_crossing = {**METRICS, "earth_contact_tolerance_s": 0.0}
    assert (
        "Earth neither rises nor sets"
        in tools.in_hours(no_crossing)[1]["Time in contact with Earth"]
    )
    smooth = tools.in_hours(METRICS, terrain_modelled=False)[1]["Longest night"]
    assert "no stated margin: the terrain is not modelled here" in smooth
    bare = {k: v for k, v in METRICS.items() if not k.endswith("_tolerance_s")}
    assert "(no margin comes with this result)" in tools.in_hours(bare)[1]["Longest night"]


def test_none_is_said_in_words_not_as_zero_hours() -> None:
    words = tools.in_hours(MALAPERT)[1]
    assert words["Longest time dark and out of contact"].startswith("none (")
    assert words["Time working alone"].startswith("none (")
    no_night = tools.in_hours({**METRICS, "longest_dark_s": 0.0})[1]
    assert no_night["Longest night"] == "none (the Sun did not set on these dates)"


def test_dates_and_times_in_words() -> None:
    assert tools.dates_words("2027-06-01T00:00:00Z", "2027-07-01T00:00:00Z") == (
        "1 Jun 2027 to 30 Jun 2027"
    )
    assert tools.dates_words("2027-03-14T00:00:00Z", "2027-04-12T12:45:00Z") == (
        "14 Mar 2027, 00:00 UTC to 12 Apr 2027, 12:45 UTC"
    )
    assert tools.when_words("2027-03-20T06:00:00+00:00") == "20 Mar 2027, 06:00 UTC"
    assert tools.dates_words(None, "2027-01-01") is None


def test_a_stretch_in_hours_with_its_start_and_end_in_words() -> None:
    arc = _arc(False, "2027-03-20T06:00:00Z", "2027-03-25T07:47:00Z", 437647.796, 61527.5)
    out = tools.arc_in_hours(arc, "night")
    assert out["duration_h"] == 121.6 and out["duration_tolerance_h"] == 17.1
    assert out["in_words"] == (
        "122 h ± 17.1 h, from 20 Mar 2027, 06:00 UTC to 25 Mar 2027, 07:47 UTC"
    )
    cut = tools.arc_in_hours({**arc, "open_start": True}, "night")["in_words"]
    assert cut.startswith("at least 122 h") and "or earlier (the dates begin inside it)" in cut


# ---------------------------------------------------------------------------
# The tools, run against canned services
# ---------------------------------------------------------------------------


async def test_get_metrics_gives_the_name_the_dates_and_the_words_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_services(monkeypatch)
    c = await run("get_metrics", {"site_id": "connecting-ridge"})
    assert c.error is None and c.result is not None
    r = c.result
    # The words come before the long blocks, so a prompt that cuts the result keeps them.
    assert list(r)[:5] == ["site_id", "name", "dates", "in_words", "provenance"]
    assert r["name"] == "Connecting Ridge"
    assert r["dates"] == "14 Mar 2027, 00:00 UTC to 12 Apr 2027, 12:45 UTC"
    assert r["in_words"]["Longest night"] == "122 h ± 17.1 h"
    assert r["longest_dark_h"] == 121.6 and r["longest_dark_tolerance_h"] == 17.1
    assert r["sunlit_s"] == METRICS["sunlit_s"]  # the seconds stay for the other agents
    assert "worked out" in r["provenance"]
    assert grounded("The longest night is 122 h ± 17.1 h, 81% of the time in sunlight.", c)
    assert not SNAKE.search(phrases(r["in_words"]))


async def test_get_windows_says_when_the_longest_stretches_happen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_services(monkeypatch)
    c = await run("get_windows", {"site_id": "connecting-ridge"})
    assert c.error is None and c.result is not None
    r = c.result
    assert r["name"] == "Connecting Ridge"
    night = r["sun"]["longest_down"]
    assert night["what"] == "night"
    assert night["in_words"].startswith("122 h ± 17.1 h, from 20 Mar 2027, 06:00 UTC")
    assert r["earth"]["longest_down"]["what"] == "time without contact"
    both = r["longest_dark_and_out_of_contact"]
    assert both["duration_h"] == 38.4
    assert "38 h (no margin is worked out for this one)" in both["in_words"]
    assert grounded(f"The longest night is {night['in_words']}.", c)


async def test_compare_sites_gives_names_words_and_which_are_too_close_to_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_services(monkeypatch)
    c = await run(
        "compare_sites",
        {
            "site_ids": ["connecting-ridge", "malapert-massif", "nowhere"],
            "rank_by": "longest_dark_s",
        },
    )
    assert c.error is None and c.result is not None
    r = c.result
    assert r["ordered_by"] == "Longest night, shortest first"
    assert [i["name"] for i in r["items"]] == ["Connecting Ridge", "Malapert massif"]
    assert r["items"][1]["in_words"]["Longest night"].startswith("at least 288 h ± 7.2 h")
    assert r["too_close_to_call"] == [["Connecting Ridge", "Malapert massif"]]
    assert r["unavailable"] == [{"site_id": "nowhere", "reason": "No terrain map covers it."}]
    # The open flags still travel (C2): a lower bound is never stated as a place.
    assert r["items"][1]["rank"] is None and r["items"][1]["longest_dark_open"] is True
    bad = await run("compare_sites", {"site_ids": ["connecting-ridge"], "rank_by": "score"})
    assert bad.error and "rank_by must be one of" in bad.error


async def test_get_site_summary_words_name_no_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_services(monkeypatch)
    c = await run("get_site", {"site_id": "connecting-ridge"})
    assert c.error is None and c.result is not None
    words = c.result["reference_summary"]["in_words"]
    assert "no margin with this coarse summary" in words["Longest night"]
    assert not SNAKE.search(phrases(words))


async def test_get_scenario_reads_the_assumptions_with_their_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_services(monkeypatch)
    c = await run("get_scenario", {"scenario_id": SCENARIO.id})
    assert c.error is None and c.result is not None
    r = c.result
    assert r["name"] == SCENARIO.name and r["mission_name"] == "IM-3"
    assert r["ready_made"] is True and r["state"] == "worked out"
    assert "none of them is written into the mission's record" in r["what_it_is"]
    rows = {a["label"]: a for a in r["assumptions"]}
    assert rows["Launch vehicle"]["value"] == "Falcon 9 Block 5"
    assert rows["Launch vehicle"]["basis"] == "Default"
    assert rows["Launch vehicle"]["source"] == "Precedent: IM-2"
    assert rows["Days on the surface"]["basis"] == "You"
    assert rows["Days on the surface"]["amount"] == 15.0
    assert rows["Landing spot"]["basis"] == "Published"
    assert {a["basis"] for a in r["assumptions"]} <= {"You", "Published", "Live", "Default"}
    steps = {s["step"]: s["state"] for s in r["steps"]}
    assert steps["Trip"] == "could not be worked out" and steps["Surface"] == "worked out"
    surface = r["results"]["Surface"]["data"]
    assert surface["dates"] == "1 Jan 2027 to 15 Jan 2027"
    assert surface["in_words"]["Longest night"].startswith("at least 360 h (no margin")
    assert r["results"]["Contact"]["available"] is False
    assert grounded("In this scenario, 15 days on the surface are assumed.", c)


async def test_get_scenario_reads_one_step_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_services(monkeypatch)
    FakeScenarios.calls.clear()
    c = await run("get_scenario", {"scenario_id": SCENARIO.id, "section": "launch"})
    assert c.result is not None and list(c.result["results"]) == ["Launch"]
    # Only `get` exists on the fake repository: a write would have raised.
    assert FakeScenarios.calls == [SCENARIO.id]
    missing = await run("get_scenario", {"scenario_id": "sc-nope"})
    assert missing.error and "no scenario" in missing.error
    bad = await run("get_scenario", {"scenario_id": SCENARIO.id, "section": "ready"})
    assert bad.error and "invalid arguments" in bad.error


def test_ask_can_call_the_scenario_and_windows_tools() -> None:
    assert {"get_scenario", "get_windows", "list_scenario_options"} <= set(chatter.CHAT_TOOLS)
    assert set(chatter.CHAT_TOOLS) <= tools.TOOL_NAMES
    decl = next(d for d in tools.TOOL_DECLARATIONS if d["name"] == "get_scenario")
    assert "scenario_id" in decl["parameters"]["properties"]
    for d in tools.TOOL_DECLARATIONS:
        assert "SECONDS" not in d["description"]
