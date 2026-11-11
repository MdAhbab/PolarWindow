"""The energy service on a synthetic Sun track (no database, no ephemeris)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.core.intervals import Run
from app.data import diviner
from app.services import energy_service as es

FIGS: dict[str, Any] = {
    "array_geometry": "top_deck_flat",
    "array_area_m2": 2.0,
    "cell_efficiency": 0.28,
    "dust_loss_fraction": 0.05,
    "battery_capacity_wh": 300.0,
    "initial_soc_fraction": 1.0,
    "avionics_w": 40.0,
    "payload_w": 10.0,
    "load_dissipation_fraction": 0.9,
    "heater_power_w": 30.0,
    "heater_setpoint_c": -10.0,
    "initial_bus_temp_c": 15.0,
    "operational_min_c": -20.0,
    "survival_min_c": -40.0,
    "bus_absorptivity": 0.3,
    "bus_side_area_m2": 3.0,
    "bus_top_area_m2": 0.0,
    "bus_emissivity": 0.8,
    "regolith_emissivity": 0.95,
    "regolith_absorptivity": 0.88,
    "view_factor": 0.5,
    "base_area_m2": 2.0,
    "radiator_emissivity": 0.85,
    "radiator_area_m2": 0.5,
    "heat_capacity_j_per_k": 2.0e5,
}
START = datetime(2026, 1, 1, tzinfo=UTC)


def fake_window() -> Any:
    """Two days: lit for the first 12 h (Sun at 10 deg), then dark."""
    t = np.arange(0.0, 48 * 3600 + 1, 900.0)
    el = np.where(t < 12 * 3600, 10.0, -5.0)
    sun = SimpleNamespace(
        t_s=t,
        az_deg=np.full_like(t, 90.0),
        el_deg=el,
        angular_radius_deg=np.full_like(t, 0.267),
        arcs=[Run(True, 0.0, 12 * 3600.0), Run(False, 12 * 3600.0, float(t[-1]))],
        arc_edge_tolerance_s=[(None, 600.0), (600.0, None)],
    )
    result = SimpleNamespace(sun=sun, start=START, site_id="x", step_s=900)
    return SimpleNamespace(
        result=result,
        site=SimpleNamespace(lat_deg=-89.0, lon_deg=0.0),
        meta=lambda cache="miss": {"uncertainty": {"notes": []}, "cache": cache},
    )


def covered(monkeypatch: pytest.MonkeyPatch) -> None:
    g = diviner.GroundTemps(
        temp_avg_k=diviner.Stat(100.0, 90.0, 110.0),
        temp_max_k=diviner.Stat(250.0, 200.0, 280.0),
        ice_depth_m=None,
        n_triangles=3,
        radius_m=1000.0,
    )
    monkeypatch.setattr(diviner, "at", lambda *a, **k: g)


def run(figs: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = es.resolve_inputs(figs or FIGS, None)
    out: dict[str, Any] = es._run(fake_window(), resolved, 1000.0)
    return out


def test_envelope_is_ordered_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    covered(monkeypatch)
    out = run()
    for band in (out["series"]["soc_wh"], out["series"]["t_bus_c"]):
        for lo, v, hi in zip(band["lo"], band["value"], band["hi"], strict=True):
            assert lo <= v <= hi
    assert len(out["series"]["t_s"]) <= es.MAX_POINTS
    assert out["ground"]["covered"] is True


def test_energy_generated_matches_hand_value(monkeypatch: pytest.MonkeyPatch) -> None:
    covered(monkeypatch)
    e = run()["key"]["energy_generated"]
    p = 0.28 * 2.0 * np.sin(np.radians(10.0)) * 1361.0 * 0.95
    assert e["value"] == pytest.approx(p * 12.0, rel=0.05)
    assert e["lo"] <= e["value"] <= e["hi"]
    assert e["provenance"] == "computed"


def test_outside_coverage_runs_the_cold_end_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diviner, "at", lambda *a, **k: None)
    out = run()
    assert out["ground"]["covered"] is False
    assert "warm end is unknown" in out["ground"]["reason"]
    assert out["series"]["t_bus_c"]["hi"][0] is None
    low = out["key"]["lowest_bus_temperature"]
    assert low["no_margin_reason"] and low["lo"] is None
    assert out["model"]["runs"] == "cold ground end only"


def test_battery_empties_without_sun_and_says_when(monkeypatch: pytest.MonkeyPatch) -> None:
    covered(monkeypatch)
    empty = run()["key"]["battery_empty_at"]
    assert empty["value"] is not None and empty["value"] > 12.0
    assert empty["value_utc"].startswith("2026-01-0")


def test_a_battery_that_never_empties_gives_null_and_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    covered(monkeypatch)
    out = run({**FIGS, "battery_capacity_wh": 1e6, "heater_power_w": 0.0})
    empty = out["key"]["battery_empty_at"]
    assert empty["value"] is None and "does not reach 0" in empty["missing_reason"]


def test_missing_figure_names_the_field() -> None:
    bad = {k: v for k, v in FIGS.items() if k != "heat_capacity_j_per_k"}
    with pytest.raises(es.BadFigure) as exc:
        es.resolve_inputs(bad, None)
    assert exc.value.field == "heat_capacity_j_per_k"


def test_vertical_faces_needs_its_own_figures() -> None:
    with pytest.raises(es.BadFigure) as exc:
        es.resolve_inputs({**FIGS, "array_geometry": "vertical_faces"}, None)
    assert exc.value.field == "face_count"


def test_inputs_are_echoed_with_provenance() -> None:
    figs = {**FIGS, "cell_efficiency": {"value": 0.3, "provenance": "assumed", "source": "typical"}}
    echoed = es.echo_inputs(es.resolve_inputs(figs, None))
    assert echoed["cell_efficiency"]["provenance"] == "assumed"
    assert echoed["avionics_w"]["provenance"] == "entered"
    unsourced = {**FIGS, "cell_efficiency": {"value": 0.3, "provenance": "published"}}
    with pytest.raises(es.BadFigure):
        es.resolve_inputs(unsourced, None)


def test_the_example_lander_is_complete_and_labelled() -> None:
    figs = es.resolve_inputs({}, "nova-c-class-assumed")
    assert {f.provenance for f in figs.values()} <= {"published", "assumed"}
    assert all(f.source for f in figs.values())


def test_no_field_is_a_score_or_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    covered(monkeypatch)
    text = json.dumps(run()).lower()
    for word in ("score", "verdict", "rating"):
        assert f'"{word}' not in text
