"""The downlink budget (ADR-20): arithmetic checked by hand, then its shape and honesty."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.api.v1.schemas.contact import LinkBudget, PassBudget
from app.core import intervals, rf_link
from app.core.quantity import Quantity
from app.core.spice import StationLook
from app.data import catalogues
from app.workers.handlers import link_budget

RX = rf_link.Receiver(
    gain_dbi=74.55,
    gain_tol_adverse_db=0.1,
    gain_tol_favourable_db=0.1,
    t_amw_k=11.65,
    t_amw_tol_adverse_k=1.0,
    t_amw_tol_favourable_k=1.0,
    zenith_clear_db=0.039,
    zenith_adverse_db=0.070,
)


def tx(eirp: float = 30.0, **kw: float) -> rf_link.Transmitter:
    return rf_link.Transmitter(eirp_dbw=eirp, frequency_ghz=8.45, required_ebn0_db=2.5, **kw)


def test_fspl_matches_a_hand_calculation() -> None:
    # 20 log10(384400) = 111.695; 20 log10(8.45) = 18.537; + 92.45 = 222.68 dB.
    assert rf_link.fspl_db(384_400.0, 8.45)[()] == pytest.approx(222.68, abs=0.01)
    # Doubling the range costs 6.02 dB.
    twice = rf_link.fspl_db([384_400.0, 768_800.0], 8.45)
    assert twice[1] - twice[0] == pytest.approx(20 * math.log10(2.0))


def test_boltzmann_constant_in_db() -> None:
    assert pytest.approx(-228.599, abs=0.001) == rf_link.K_B_DBW_HZ_K


def test_air_mass_is_flat_earth_above_6_degrees_and_finite_below() -> None:
    assert rf_link.air_mass(90.0)[()] == pytest.approx(1.0)
    assert rf_link.air_mass(30.0)[()] == pytest.approx(2.0)
    low = rf_link.air_mass(np.array([6.0, 3.0, 1.0, 0.0, -2.0]))
    assert np.all(np.isfinite(low))
    assert np.all(np.diff(low) >= 0)  # lower is longer, and the clip keeps the last two equal
    assert low[0] == pytest.approx(1.0 / math.sin(math.radians(6.0)))


def test_sky_noise_follows_module_105() -> None:
    a = np.array([0.039])
    loss = 10 ** (0.039 / 10)
    want = (255 + 25 * 0.25) * (1 - 1 / loss) + 2.725 / loss
    assert rf_link.sky_noise_k(a, 0.25)[0] == pytest.approx(want)
    # The model reproduces the zenith sky temperatures published in modules 101 and 104
    # (Table 4 / Table 11) from the zenith attenuations of modules 105: Goldstone, Canberra, Madrid.
    for zen, published in ((0.039, 5.04), (0.045, 5.39), (0.043, 5.27)):
        assert rf_link.sky_noise_k(np.array([zen]), 0.25)[0] == pytest.approx(published, abs=0.02)


def test_ebn0_arithmetic() -> None:
    d, el = 384_400.0, 40.0
    b = rf_link.evaluate([d], [el], RX, tx(30.0))
    a = rf_link.atmosphere_db(el, 0.039)[()]
    gt = RX.gain_dbi - 10 * math.log10(RX.t_amw_k + rf_link.sky_noise_k(np.array(a), 0.25))
    want_pr = 30.0 - rf_link.fspl_db(d, 8.45) - a + gt - 10 * math.log10(1.380649e-23)
    assert b.pr_over_n0_dbhz.value[0] == pytest.approx(want_pr)
    e = rf_link.ebn0_db(b, 10_000.0)
    assert e.value[0] == pytest.approx(want_pr - 40.0)
    # Margin is Eb/N0 over the coding's requirement; the rate that closes at zero margin
    # has exactly the required Eb/N0.
    rate = rf_link.max_rate_bps(b).value[0]
    assert rf_link.margin_db(b, float(rate)).value[0] == pytest.approx(0.0, abs=1e-9)


def test_required_margin_lowers_the_rate() -> None:
    d, el = [384_400.0], [40.0]
    plain = rf_link.max_rate_bps(rf_link.evaluate(d, el, RX, tx())).value[0]
    held = rf_link.max_rate_bps(rf_link.evaluate(d, el, RX, tx(required_margin_db=3.0))).value[0]
    assert held == pytest.approx(plain / 10**0.3)


def test_rate_grows_with_eirp_and_elevation() -> None:
    d = [384_400.0]
    rates = [
        rf_link.max_rate_bps(rf_link.evaluate(d, [40.0], RX, tx(e))).value[0]
        for e in (20.0, 25.0, 30.0)
    ]
    assert rates[0] < rates[1] < rates[2]
    assert rates[1] / rates[0] == pytest.approx(10**0.5)
    els = np.array([3.0, 6.0, 10.0, 20.0, 45.0, 90.0])
    b = rf_link.evaluate(np.full(els.shape, 384_400.0), els, RX, tx())
    r = rf_link.max_rate_bps(b)
    assert np.all(np.diff(r.value) > 0)
    assert np.all(np.diff(r.lo) > 0)


def test_envelope_orders_lo_value_hi() -> None:
    els = np.linspace(2.0, 90.0, 30)
    b = rf_link.evaluate(np.full(els.shape, 400_000.0), els, RX, tx(eirp_tol_db=1.0))
    for env in (
        b.atmosphere_db,
        b.g_over_t_dbk,
        b.pr_over_n0_dbhz,
        rf_link.ebn0_db(b, 1e4),
        rf_link.margin_db(b, 1e4),
        rf_link.max_rate_bps(b),
    ):
        assert np.all(env.lo <= env.value) and np.all(env.value <= env.hi)
    # The adverse end is strictly worse for the rate, the favourable end strictly better.
    r = rf_link.max_rate_bps(b)
    assert np.all(r.lo < r.value) and np.all(r.value < r.hi)
    # Clear sky is the lower end of a loss.
    assert np.all(b.atmosphere_db.hi > b.atmosphere_db.lo)


def test_the_envelope_refuses_a_value_outside_its_ends() -> None:
    with pytest.raises(ValueError):
        rf_link.Envelope(np.array([2.0]), np.array([1.0]), np.array([1.5]))


def test_bad_inputs_are_refused() -> None:
    with pytest.raises(ValueError):
        rf_link.evaluate([1e5], [10.0, 20.0], RX, tx())
    with pytest.raises(ValueError):
        rf_link.fspl_db([0.0], 8.45)
    with pytest.raises(ValueError):
        rf_link.evaluate([1e5], [10.0], RX, tx(eirp_tol_db=-1.0))


def test_missing_eirp_keeps_line_of_sight_only() -> None:
    miss = rf_link.missing_inputs(eirp_dbw=None, frequency_mhz=None, required_ebn0_db=None)
    assert rf_link.line_of_sight_note(miss) == rf_link.LINE_OF_SIGHT_ONLY
    assert rf_link.LINE_OF_SIGHT_ONLY.startswith("Line of sight only")
    ok, _ = link_budget.can_run(None)
    assert not ok
    # With the EIRP but not the coding, it still says line of sight only, and names the gap.
    miss = rf_link.missing_inputs(eirp_dbw=30.0, frequency_mhz=8450.0, required_ebn0_db=None)
    note = rf_link.line_of_sight_note(miss)
    assert note.startswith("Line of sight only") and "Eb/N0" in note
    assert rf_link.missing_inputs(eirp_dbw=30.0, frequency_mhz=8450.0, required_ebn0_db=2.5) == []


def test_every_quantity_helper_output_is_a_valid_quantity() -> None:
    b = rf_link.evaluate([384_400.0, 400_000.0], [30.0, 8.0], RX, tx(eirp_tol_db=0.5))
    for env, unit in (
        (b.atmosphere_db, "dB"),
        (b.g_over_t_dbk, "dB/K"),
        (rf_link.max_rate_bps(b), "bit/s"),
        (rf_link.margin_db(b, 5_000.0), "dB"),
    ):
        for i in range(2):
            q = rf_link.quantity(env, i, unit)
            assert isinstance(q, Quantity) and q.value is not None
            lo, hi = q.bounds or (q.value, q.value)
            assert lo <= q.value <= hi
    # An envelope with no spread says why it has no margin instead of faking one.
    flat = rf_link.Envelope(np.array([3.0]), np.array([3.0]), np.array([3.0]))
    assert rf_link.quantity(flat, 0, "dB").no_margin_reason


def _li(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "eirp_dbw": 30.0,
        "eirp_tol_db": 0.5,
        "frequency_mhz": 8445.0,
        "required_ebn0_db": 2.5,
        "required_margin_db": 3.0,
        "data_rates_kbps": [100.0, 2000.0],
        "provenance": "entered",
        "source": "entered on the mission record for test",
    }
    base.update(kw)
    return base


def test_pass_budget_through_the_contact_shapes() -> None:
    cat = catalogues.load("ground_stations")
    dss14 = cat.get("dss-14")
    dss24 = cat.get("dss-24")  # no published X-band figures: no budget, said so
    assert dss14.rx_x is not None and dss24.rx_x is None
    t = np.arange(0.0, 3600.0, 60.0)
    el = 8.0 + 52.0 * np.sin(np.pi * t / 3600.0)  # rises, peaks at 60 deg, sets
    look = StationLook(
        station="DSS-14", az_deg=np.zeros_like(t), el_deg=el, range_m=np.full_like(t, 3.8e8)
    )
    look24 = StationLook(
        station="DSS-24", az_deg=np.zeros_like(t), el_deg=el, range_m=np.full_like(t, 3.8e8)
    )
    runs = [intervals.Run(True, 0.0, 3540.0)]
    li = _li()
    out = link_budget.stations(
        li, [dss14, dss24], [look, look24], t, {"dss-14": runs, "dss-24": runs}
    )
    assert set(out) == {"dss-14"}
    p = PassBudget.model_validate(out["dss-14"]["passes"][0])
    vals = [
        p.peak.elevation_deg.value,
        p.peak.max_rate_kbps.value,
        p.edge.max_rate_kbps.value,
        p.peak.margins[0].margin_db.value,
        p.peak.margins[1].margin_db.value,
    ]
    assert all(v is not None for v in vals)
    elev, peak_rate, edge_rate, margin_slow, margin_fast = (float(v) for v in vals if v is not None)
    assert elev == pytest.approx(60.0, abs=1.0)
    assert peak_rate > edge_rate > 0
    assert [m.rate_kbps.value for m in p.peak.margins] == [100.0, 2000.0]
    assert margin_slow > margin_fast
    m = p.peak.max_rate_kbps
    assert m.lo is not None and m.hi is not None and m.lo < peak_rate < m.hi
    b = link_budget.basis(li, [dss14, dss24])
    LinkBudget.model_validate(b)
    assert b["stations_without_figures"] == ["dss-24"]
    assert b["stations"][0]["gain_dbi"]["provenance"] == "published"
    assert b["stations"][0]["gain_dbi"]["source"].startswith("https://deepspace.jpl.nasa.gov/")
    note = link_budget.ran_note(li, b)
    assert "30.0 dBW" in note and "entered on the mission record" in note
    assert "DSS-24" in note and "not modelled" in note


def test_station_figures_are_sourced() -> None:
    for g in catalogues.load("ground_stations").records:
        if g.rx_x is not None:
            assert g.rx_x.source_url.startswith("https://deepspace.jpl.nasa.gov/dsndocs/810-005/")
            assert g.rx_x.source_url in {s.url for s in g.sources}
        else:
            assert "rx_x" in g.unconfirmed_fields
        assert g.atmosphere_x is not None
        assert g.atmosphere_x.zenith_clear_db <= g.atmosphere_x.zenith_adverse_db
