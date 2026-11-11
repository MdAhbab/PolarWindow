"""The mesh physics and rules (pure): two-ray loss, the radio state machine, the helper
guard, the buffer, minimum-energy routing."""

from __future__ import annotations

import numpy as np
import pytest

from app.core import mesh as m

F = 2.4e9


def test_two_ray_tends_to_free_space_at_short_range() -> None:
    d = 0.1  # far inside the antenna heights, so the reflected ray is much longer
    two = float(m.two_ray_loss_db(d, 5.0, 5.0, F, 3.0, "horizontal"))
    fs = float(m.free_space_loss_db(d, F))
    assert two == pytest.approx(fs, abs=0.5)


@pytest.mark.parametrize("pol", ["horizontal", "vertical"])
def test_two_ray_falls_as_d4_beyond_the_break_distance(pol: str) -> None:
    h = 2.0
    brk = m.break_distance_m(h, h, F)
    assert brk == pytest.approx(4 * h * h / m.wavelength_m(F))
    d1, d2 = 40 * brk, 400 * brk
    a = float(m.two_ray_loss_db(d1, h, h, F, 3.0, pol))  # type: ignore[arg-type]
    b = float(m.two_ray_loss_db(d2, h, h, F, 3.0, pol))  # type: ignore[arg-type]
    assert b - a == pytest.approx(40.0, abs=0.5)  # 10x the range is 40 dB, not 20


def test_state_machine_at_under_and_over_the_threshold() -> None:
    t = np.arange(0.0, 9001.0, 600.0)
    healthy = np.array([t_ < 1000 or t_ >= 7000 for t_ in t])
    states, events = m.run_state_machine(t, healthy, 3600.0)
    by_t = dict(zip(t, states, strict=True))
    assert by_t[0.0] == m.RadioState.DEEP_SLEEP
    assert by_t[1200.0] == m.RadioState.STANDBY  # lost from here
    assert by_t[4200.0] == m.RadioState.STANDBY  # lost 3000 s: just under
    assert by_t[4800.0] == m.RadioState.STANDBY  # lost exactly 3600 s: not longer than it
    assert by_t[5400.0] == m.RadioState.ACTIVE_RELAY  # 4200 s: over
    assert by_t[7200.0] == m.RadioState.DEEP_SLEEP  # link back: immediately asleep
    assert [e.to_state for e in events] == [
        m.RadioState.STANDBY,
        m.RadioState.ACTIVE_RELAY,
        m.RadioState.DEEP_SLEEP,
    ]


def guard(**over: object) -> str | None:
    kw: dict[str, object] = {
        "sunlit": True,
        "soc_fraction": 0.8,
        "soc_cutoff_fraction": 0.3,
        "energy_today_wh": 1.0,
        "quota_wh": 10.0,
        "forwarding_power_w": 2.0,
        "power_cap_w": 5.0,
    }
    kw.update(over)
    return m.guard_refusal(**kw)  # type: ignore[arg-type]


def test_guard_allows_when_every_rule_holds() -> None:
    assert guard() is None


def test_guard_names_the_rule_that_refused() -> None:
    assert guard(soc_fraction=0.29) == m.RULE_LOW_CHARGE
    assert guard(soc_fraction=0.3) is None  # at the cut-off is allowed
    assert guard(sunlit=False) == m.RULE_NIGHT
    assert guard(energy_today_wh=10.0) == m.RULE_QUOTA
    assert guard(energy_today_wh=9.99) is None
    assert guard(forwarding_power_w=5.1) == m.RULE_POWER_CAP


def test_buffer_cap_drops_and_counts() -> None:
    s = m.relay_step(buffer_bits=0.0, inflow_bits=1000.0, out_bits=100.0, buffer_cap_bits=300.0)
    assert (s.sent_bits, s.dropped_bits, s.buffer_bits) == (100.0, 600.0, 300.0)
    s = m.relay_step(buffer_bits=0.0, inflow_bits=200.0, out_bits=0.0, buffer_cap_bits=300.0)
    assert (s.sent_bits, s.dropped_bits, s.buffer_bits) == (0.0, 0.0, 200.0)


def test_own_traffic_preempts_forwarding() -> None:
    assert m.spare_capacity_bps(1000.0, 400.0) == 600.0
    assert m.spare_capacity_bps(1000.0, 1000.0) == 0.0
    assert m.spare_capacity_bps(1000.0, 5000.0) == 0.0


def test_dijkstra_prefers_two_cheap_hops_over_one_costly() -> None:
    edges = {"a": {"b": 1.0, "c": 10.0}, "b": {"c": 1.0}}
    path, cost = m.min_energy_path(edges, "a", {"c"}, {"b", "c"}) or ([], 0.0)
    assert path == ["a", "b", "c"] and cost == 2.0
    # if b may not help, the costly direct hop is what is left
    path, cost = m.min_energy_path(edges, "a", {"c"}, {"c"}) or ([], 0.0)
    assert path == ["a", "c"] and cost == 10.0


def test_isolated_node_has_no_path() -> None:
    assert m.min_energy_path({}, "a", {"c"}, {"b", "c"}) is None
    assert m.min_energy_path({"a": {}}, "a", {"c"}, {"c"}) is None


def test_no_hidden_radio_default() -> None:
    with pytest.raises(TypeError):
        m.Radio(frequency_hz=F)  # type: ignore[call-arg]


def test_intervals_and_longest_run() -> None:
    assert m.intervals([1, 1, 2, 2, 2, 1]) == [(0, 2, 1), (2, 5, 2), (5, 6, 1)]
    t = np.arange(0.0, 6001.0, 1000.0)
    flag = np.array([False, True, True, False, True, False, False])
    length, at, open_ = m.longest_run(t, flag)
    assert (length, at, open_) == (2000.0, 1000.0, False)
