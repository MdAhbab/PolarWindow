"""The mesh service on a flat synthetic terrain with scripted skies (no DEM, no database)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.api.v1.schemas.mesh import MeshRequest, MeshResponse
from app.core import mesh as core
from app.services import mesh_service as ms
from app.services import site_service

START = datetime(2026, 1, 1, tzinfo=UTC)
DAY = 86400.0
RADIO: dict[str, Any] = {
    "frequency_hz": 2.4e9,
    "tx_power_w": 1.0,
    "forwarding_tx_power_w": 1.0,
    "tx_efficiency": 0.5,
    "antenna_gain_dbi": 3.0,
    "bandwidth_hz": 1e6,
    "noise_figure_db": 5.0,
    "snr_threshold_db": 3.0,
    "eps_r": 3.0,
    "polarisation": "horizontal",
}
GUARD: dict[str, Any] = {
    "soc_cutoff_fraction": 0.3,
    "quota_share_per_lunar_day": 1.0,
    "max_forwarding_power_w": 5.0,
    "buffer_bytes": 1e9,
}
LANDER_AT = {"east_m": 0.0, "north_m": 0.0}
ROVER_AT = {"east_m": 200.0, "north_m": 0.0}

Script = Callable[[int], Any]


def node(nid: str, at: dict[str, float], **kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": nid,
        "position": at,
        "antenna_height_m": 5.0,  # the first Fresnel zone at 2.4 GHz is ~2.5 m deep at 200 m
        "battery_capacity_wh": 100.0,
        "initial_soc_fraction": 1.0,
        "own_traffic_bps": 0.0,
        "may_help": False,
    }
    d.update(kw)
    return d


def lander(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"may_help": True, "earth_uplink_bps": 1e5, "earth_uplink_power_w": 20.0}
    base.update(kw)
    return node("lander", LANDER_AT, **base)


def window(days: float = 10.0) -> Any:
    t = np.arange(0.0, days * DAY + 1, 3600.0)
    track = SimpleNamespace(t_s=t, az_deg=np.zeros_like(t), el_deg=np.zeros_like(t))
    result = SimpleNamespace(earth=track, sun=track, start=START, site_id="x", step_s=3600)
    return SimpleNamespace(
        result=result,
        site=SimpleNamespace(id="x", lat_deg=-89.0, lon_deg=0.0),
        meta=lambda cache="miss": {
            "computed_at": START.isoformat(),
            "resolution": {
                "azimuth_deg": 0.25,
                "azimuth_count": 1440,
                "time_step_s": 3600,
                "max_range_m": 20000.0,
                "dem_product": "TEST",
                "dem_resolution_m": 5.0,
                "ephemeris": "test",
                "frame": "test",
            },
            "uncertainty": {
                "dem_vertical_error_m": 1.0,
                "dem_resolution_m": 5.0,
                "coverage": 1.0,
                "horizon_el_deg": 0.1,
                "edge_timing_s": 60.0,
                "grazing": False,
                "penumbra_sun_deg": 0.27,
                "penumbra_earth_deg": 0.27,
                "notes": [],
            },
            "engine_version": "test",
            "cache": cache,
        },
    )


def flat(
    monkeypatch: pytest.MonkeyPatch,
    earth: dict[tuple[float, float], Script],
    sun: Script | None = None,
) -> None:
    """Flat ground; each position's Earth view (and the Sun) is scripted per step."""

    def z(x: Any, y: Any) -> Any:
        return np.zeros(np.shape(x))

    monkeypatch.setattr(ms, "_terrain", lambda *a: ms.Terrain(z, z, 5.0, ["TEST"], 1.0))

    def skies(cw: Any, terrain: Any, pos: tuple[float, float]) -> Any:
        n = len(cw.result.earth.t_s)
        lit = np.ones(n, dtype=bool) if sun is None else sun(n)
        return ms._Skies(earth[pos](n), np.zeros(n, dtype=bool), lit)

    monkeypatch.setattr(ms, "_skies", skies)


def always(n: int) -> Any:
    return np.ones(n, dtype=bool)


def never(n: int) -> Any:
    return np.zeros(n, dtype=bool)


def rover_view(n: int) -> Any:  # sees Earth for 1 day, none for 5 days, then again
    t = np.arange(n) * 3600.0
    return (t < 1 * DAY) | (t >= 6 * DAY)


def run(nodes: list[dict[str, Any]], guard: dict[str, Any] | None = None) -> dict[str, Any]:
    rad = core.Radio(**RADIO)
    out: dict[str, Any] = ms._run(
        window(), [ms._node(d) for d in nodes], rad, guard or GUARD, 7200.0, 300.0
    )
    return out


def helper(out: dict[str, Any]) -> dict[str, Any]:
    h: dict[str, Any] = next(h for h in out["helpers"] if h["id"] == "lander")
    return h


def rover(out: dict[str, Any]) -> dict[str, Any]:
    r: dict[str, Any] = next(n for n in out["nodes"] if n["id"] == "r1")
    return r


def refused_h(out: dict[str, Any]) -> dict[str, float]:
    r: dict[str, float] = helper(out)["refused_hours_by_rule"]
    return r


def test_mesh_shortens_the_wait_and_never_lengthens_it(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): rover_view})
    out = run([lander(), node("r1", ROVER_AT, own_traffic_bps=1e3)])
    r1 = rover(out)
    lw = r1["longest_without_path_to_earth"]
    assert lw["direct_only"]["value"] == pytest.approx(120.0)  # five days, in hours
    assert 0.0 < lw["with_mesh"]["value"] < lw["direct_only"]["value"]
    assert any(x["status"] == "mesh" and x["path"] == ["r1", "lander"] for x in r1["routes"])
    assert helper(out)["forwarded_mb"]["value"] > 0
    assert r1["delivered_via_mesh_mb"] > 0


def test_mesh_equals_direct_only_when_nobody_may_help(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): rover_view})
    out = run([lander(may_help=False), node("r1", ROVER_AT)])
    lw = rover(out)["longest_without_path_to_earth"]
    assert lw["with_mesh"]["value"] == lw["direct_only"]["value"]


def test_isolated_node_with_no_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(200.0, 0.0): never})
    out = run([node("r1", ROVER_AT)])
    statuses = {x["status"] for x in out["nodes"][0]["routes"]}
    assert "isolated" in statuses and statuses <= {"waiting", "isolated"}


def test_forwarding_stops_below_the_charge_cutoff(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): never})
    out = run([lander(initial_soc_fraction=0.2), node("r1", ROVER_AT)])
    assert refused_h(out)["charge_below_cutoff"] > 0
    assert helper(out)["forwarded_mb"]["value"] == 0.0


def test_forwarding_stops_in_the_helpers_night(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(
        monkeypatch,
        {(0.0, 0.0): always, (200.0, 0.0): never},
        sun=lambda n: np.arange(n) * 3600.0 >= 5 * DAY,
    )
    out = run([lander(), node("r1", ROVER_AT, own_traffic_bps=1e3)])
    assert refused_h(out)["night"] > 0
    assert helper(out)["forwarded_mb"]["value"] > 0  # once the Sun is up
    assert any(
        x["status"] == "refused" and x["refused_by"][0]["rule"] == "night"
        for x in rover(out)["routes"]
    )


def test_forwarding_stops_at_the_energy_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): never})
    guard = {**GUARD, "quota_share_per_lunar_day": 0.001}  # 0.1 Wh of 100
    out = run([lander(), node("r1", ROVER_AT, own_traffic_bps=5e4)], guard)
    assert refused_h(out)["energy_quota"] > 0
    # one step may overshoot the quota; it is not then repeated
    assert helper(out)["energy_spent_wh"]["value"] < 25.0


def test_power_cap_names_its_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): never})
    out = run([lander(), node("r1", ROVER_AT)], {**GUARD, "max_forwarding_power_w": 0.5})
    assert refused_h(out)["power_cap"] > 0
    assert helper(out)["forwarded_mb"]["value"] == 0.0


def test_buffer_cap_drops_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): never})
    guard = {**GUARD, "buffer_bytes": 1000.0}
    # the rover sends 1 kb/s; the lander's Earth uplink is slower
    out = run([lander(earth_uplink_bps=500.0), node("r1", ROVER_AT, own_traffic_bps=1e3)], guard)
    h = helper(out)
    assert h["dropped_mb"]["value"] > 0
    assert h["buffered_at_end_mb"]["value"] <= 1000.0 * 8 / 8e6 + 1e-9


def test_helpers_own_traffic_preempts_forwarding(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): never})
    out = run(
        [
            lander(earth_uplink_bps=1e5, own_traffic_bps=1e5),  # its own traffic fills the uplink
            node("r1", ROVER_AT, own_traffic_bps=1e3),
        ]
    )
    assert any(x["status"] == "no_capacity" for x in rover(out)["routes"])
    assert helper(out)["forwarded_mb"]["value"] == 0.0


def test_request_schema_requires_every_radio_figure() -> None:
    body = {
        "nodes": [{**lander(), "id": "l"}],
        "radio": {k: v for k, v in RADIO.items() if k != "noise_figure_db"},
        "guard": GUARD,
        "loss_threshold_s": 600,
    }
    with pytest.raises(ValueError, match="noise_figure_db"):
        MeshRequest.model_validate(body)


async def _simulate(radio: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = await ms.simulate(
        None,  # type: ignore[arg-type]
        "x",
        START,
        START,
        3600,
        [lander(), node("r1", ROVER_AT, own_traffic_bps=1e3)],
        radio,
        GUARD,
        7200.0,
    )
    return out


def test_simulate_end_to_end_and_response_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): rover_view})

    async def fake_compute(*a: Any, **k: Any) -> Any:
        return window()

    monkeypatch.setattr(site_service, "compute", fake_compute)
    out = asyncio.run(_simulate(RADIO))
    MeshResponse.model_validate(out)
    assert out["not_modelled"]
    assert out["inputs"]["radio"]["tx_power_w"]["provenance"] == "entered"


def test_a_bad_radio_figure_is_named() -> None:
    with pytest.raises(ms.BadMesh) as e:
        asyncio.run(_simulate({**RADIO, "tx_efficiency": 0.0}))
    assert e.value.field == "radio" and "tx_efficiency" in e.value.why


def walk(o: Any) -> Any:
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def test_no_composite_names_in_the_response(monkeypatch: pytest.MonkeyPatch) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): rover_view})
    out = run([lander(), node("r1", ROVER_AT)])
    banned = ("score", "verdict", "rating", "go_no_go", "suitability")
    bad = [k for k in walk(out) if isinstance(k, str) and any(b in k.lower() for b in banned)]
    assert bad == []


def test_low_antennas_on_flat_ground_still_link(monkeypatch: pytest.MonkeyPatch) -> None:
    """At 2 m the ground is inside the first Fresnel zone, as it always is between low
    antennas. The two-ray loss carries that; the terrain test is the line between them."""
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): rover_view})
    out = run(
        [
            lander(antenna_height_m=2.0),
            node("r1", ROVER_AT, own_traffic_bps=1e3, antenna_height_m=2.0),
        ]
    )
    link = next(x for x in out["links"] if {x["a"], x["b"]} == {"lander", "r1"})
    assert link["terrain_sight"] == "clear"
    assert link["terrain_fresnel"] != "clear"
    assert link["usable"] is True
    lw = rover(out)["longest_without_path_to_earth"]
    assert lw["with_mesh"]["value"] < lw["direct_only"]["value"]


def test_the_mesh_figure_comes_with_what_uncertain_links_would_give(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flat(monkeypatch, {(0.0, 0.0): always, (200.0, 0.0): rover_view})
    nodes = [ms._node(d) for d in (lander(), node("r1", ROVER_AT, own_traffic_bps=1e3))]
    out = ms._both(window(), nodes, core.Radio(**RADIO), GUARD, 7200.0, 300.0)
    lw = rover(out)["longest_without_path_to_earth"]
    hopeful = lw["with_mesh_if_uncertain_links_hold"]
    # Counting on more links can only shorten the wait, never lengthen it.
    assert hopeful["value"] <= lw["with_mesh"]["value"] <= lw["direct_only"]["value"]
    assert hopeful["unit"] == "h"
