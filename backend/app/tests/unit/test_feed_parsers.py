"""Every feed parser against a response recorded from the real service.

Fixtures in ``app/tests/fixtures/feeds/`` were fetched on 2026-09-26 (UTC)
from the live endpoints and trimmed to keep the repository small; nothing in
them was edited by hand. Tests never touch the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.feeds.adapters import donki, dsn_now, ll2, ndbc, nomads, nws, swpc
from app.feeds.base import ParseError

FX = Path(__file__).resolve().parents[1] / "fixtures" / "feeds"


def raw(name: str) -> bytes:
    return (FX / name).read_bytes()


# --- SWPC ---------------------------------------------------------------------


def test_kp_reads_the_new_key_value_format() -> None:
    p = swpc.parse_kp(raw("swpc_kp.json"))
    latest = p.values["latest"]
    assert 0 <= latest["kp"] <= 9
    assert p.issued_at is not None and p.issued_at.tzinfo is not None
    assert len(p.values["series"]) > 20


def test_kp_refuses_the_old_list_of_lists_format() -> None:
    old = json.dumps(
        [
            ["time_tag", "Kp", "a_running", "station_count"],
            ["2026-09-19 00:00:00.000", "2.33", "9", "8"],
        ]
    ).encode()
    with pytest.raises(ParseError, match="list of objects"):
        swpc.parse_kp(old)


def test_protons_keep_the_two_alert_channels() -> None:
    p = swpc.parse_protons(raw("swpc_protons_6h.json"))
    assert p.values["unit"] == "pfu"
    for ch in (">=10 MeV", ">=100 MeV"):
        assert p.values["latest"][ch]["pfu"] >= 0
        assert p.values["series"][ch]


def test_xrays_give_a_flare_class() -> None:
    p = swpc.parse_xrays(raw("swpc_xrays_6h.json"))
    assert p.values["latest"]["class"][0] in "ABCMX"
    assert swpc.xray_class(2.3e-5) == "M2.3"
    assert swpc.xray_class(1.2e-4) == "X1.2"
    assert swpc.xray_class(5e-9) == "A0.5"


def test_solar_wind_keeps_only_active_rows_in_si() -> None:
    rows = json.loads(raw("swpc_rtsw_wind.json"))
    p = swpc.parse_rtsw_wind(raw("swpc_rtsw_wind.json"))
    active_sources = {r["source"] for r in rows if r["active"]}
    assert set(p.values["sources"]) <= active_sources
    v = p.values["latest"]["speed_m_s"]
    assert v is None or 1e5 < v < 3.5e6  # m/s, not km/s


def test_solar_wind_without_the_active_flag_is_refused() -> None:
    with pytest.raises(ParseError, match="active"):
        swpc.parse_rtsw_wind(json.dumps([{"time_tag": "2026-09-26T00:00:00"}]).encode())


def test_magnetic_field_in_tesla() -> None:
    p = swpc.parse_rtsw_mag(raw("swpc_rtsw_mag.json"))
    bt = p.values["latest"]["bt_t"]
    assert bt is None or 0 <= bt < 5e-7


def test_alerts_and_the_three_day_forecast_verbatim() -> None:
    a = swpc.parse_alerts(raw("swpc_alerts.json"))
    assert a.values["alerts"][0]["headline"]
    f = swpc.parse_3day(raw("swpc_3day.txt"))
    assert f.issued_at == datetime(2026, 9, 26, 12, 30, tzinfo=UTC)
    assert f.values["s1_or_greater_pct"] == [1, 1, 1]
    assert f.values["r1_r2_pct"] == [10, 10, 5]
    assert f.values["kp_max_expected"] == 4.0
    assert "Solar Radiation Storm Forecast" in f.values["text"]


def test_f107() -> None:
    p = swpc.parse_f107(raw("swpc_f107.json"))
    assert 50 < p.values["latest"]["sfu"] < 400


def test_a_value_outside_its_physical_range_is_dropped_and_said() -> None:
    body = json.dumps(
        [
            {"time_tag": "2026-09-26T00:00:00", "Kp": 2.0, "a_running": 7, "station_count": 8},
            {"time_tag": "2026-09-26T03:00:00", "Kp": 42.0, "a_running": 7, "station_count": 8},
        ]
    ).encode()
    p = swpc.parse_kp(body)
    assert p.values["latest"]["kp"] == 2.0
    assert any("outside the physical range" in i for i in p.issues)


def test_not_json_is_a_parse_error() -> None:
    with pytest.raises(ParseError):
        swpc.parse_kp(b"<html>maintenance</html>")


# --- DONKI ----------------------------------------------------------------------


def test_donki_events() -> None:
    c = donki.parse_cme(raw("donki_cme.json"))
    assert c.values["count"] == len(json.loads(raw("donki_cme.json")))
    f = donki.parse_flr(raw("donki_flr.json"))
    assert f.values["events"][0]["class"]
    s = donki.parse_sep(raw("donki_sep.json"))
    assert s.values["events"][0]["time"].endswith("Z")


def test_donki_never_stores_the_key() -> None:
    p = donki.products(datetime(2026, 9, 26, tzinfo=UTC))[0]
    assert "api_key" not in p.public_url()
    assert "startDate=2026-08-27" in p.public_url()


# --- DSN Now, NWS, NDBC, LL2 ----------------------------------------------------------


def test_dsn_now_tracks() -> None:
    p = dsn_now.parse(raw("dsn_now.xml"))
    names = {s["name"] for s in p.values["stations"]}
    assert names == {"gdscc", "mdscc", "cdscc"}
    assert all(t["spacecraft"] not in dsn_now.NOT_A_SPACECRAFT for t in p.values["tracks"])
    assert p.issued_at is not None


def test_dsn_now_refuses_a_changed_layout() -> None:
    with pytest.raises(ParseError):
        dsn_now.parse(b"<network><antenna/></network>")
    with pytest.raises(ParseError):
        dsn_now.parse(b"<!DOCTYPE x [<!ENTITY a 'b'>]><dsn>&a;</dsn>")


def test_nws_grid_expands_stretches_to_hours_in_si() -> None:
    p = nws.parse_grid(raw("nws_grid.json"))
    v = p.values
    assert v["office"] == "MLB"
    n = len(v["times"])
    assert all(len(v[k]) == n for k in ("wind_speed_m_s", "temperature_k", "p_thunder_frac"))
    first = next(x for x in v["wind_speed_m_s"] if x is not None)
    assert first == pytest.approx(7.408 / 3.6)  # the grid's first value, km/h -> m/s
    t = next(x for x in v["temperature_k"] if x is not None)
    assert 250 < t < 320


def test_nws_duration() -> None:
    assert nws.duration("P2DT12H").total_seconds() == 60 * 3600
    assert nws.duration("PT1H").total_seconds() == 3600
    with pytest.raises(ParseError):
        nws.duration("1 hour")


def test_nws_alerts() -> None:
    p = nws.parse_alerts(raw("nws_alerts.json"))
    assert p.values["alerts"][0]["event"] == "Rip Current Statement"


def test_ndbc_reads_missing_as_none_and_converts() -> None:
    p = ndbc.parse(raw("ndbc_41009.txt"))
    latest = p.values["latest"]
    assert latest["wind_m_s"]["value"] == 6.0
    assert latest["wave_height_m"]["value"] == 2.0  # first row with a wave height
    assert latest["pressure_pa"]["value"] == pytest.approx(101270.0)
    assert latest["air_temp_k"]["value"] == pytest.approx(25.5 + 273.15)


def test_ll2_reads_launches_and_booster_landings() -> None:
    p = ll2.parse(raw("ll2_upcoming.json"))
    byname = {x["name"]: x for x in p.values["launches"]}
    griffin = next(v for k, v in byname.items() if "Griffin" in k)
    assert griffin["pad_name"] == "Launch Complex 39A"
    assert griffin["net_precision"] == "Month"
    ussf = next(v for k, v in byname.items() if "USSF-385" in k)
    assert ussf["landings"][0]["type"] == "ASDS"
    assert ussf["landings"][0]["downrange_km"] == 574.0


# --- GRIB through ecCodes ---------------------------------------------------------------


def test_gefs_subset_at_the_pads() -> None:
    body = raw("gefs_gep01_f024_subset.grb2") + raw("gefs_gep01_f024b_subset.grb2")
    parse = nomads.parse_points([("ksc-lc-39a", 28.60823, -80.60428)], "GEFS", 31)
    p = parse(body)
    lead = p.values["points"]["ksc-lc-39a"]["leads"]["24"]
    member = lead["members"]["1"]
    assert 280 < member["t2m_k"] < 310
    assert {"u10_m_s", "v10_m_s", "u80_m_s", "v80_m_s", "gust_m_s", "cloud_frac"} <= set(member)
    assert 0 <= member["cloud_frac"] <= 1
    assert p.values["points"]["ksc-lc-39a"]["method"] == "bilinear"
    assert p.issued_at == datetime(2026, 9, 26, 12, tzinfo=UTC)
    assert any("1 of 31 runs" in i for i in p.issues)  # the fixture holds one run only


def test_hrrr_subset_nearest_point() -> None:
    parse = nomads.parse_points([("ksc-lc-39a", 28.60823, -80.60428)], "HRRR", 1)
    p = parse(raw("hrrr_f06_subset.grb2"))
    pad = p.values["points"]["ksc-lc-39a"]
    assert pad["method"] == "nearest" and pad["distance_km"] < 2.5
    m = pad["leads"]["6"]["members"]["0"]
    assert {"u10_m_s", "v10_m_s", "u80_m_s", "gust_m_s"} <= set(m)


def test_gfswave_over_the_sea_downrange() -> None:
    # Fetched 2026-09-27 (run of 2026-09-26 00 UTC, 24 h), the product's own box.
    pts = nomads.wave_points("florida")
    assert len(pts) == 7 * 11 and ("w28n077w", 28.0, -77.0) in pts
    p = nomads.parse_points(pts, "GFS-Wave", 1)(raw("gfswave_florida_f024.grb2"))
    sea = p.values["points"]["w28n077w"]["leads"]["24"]["members"]["0"]
    assert 0.0 < sea["wave_height_m"] < 15.0 and 1.0 < sea["wave_period_s"] < 25.0
    assert 0.0 <= sea["wind_m_s"] < 60.0
    assert p.issued_at == datetime(2026, 9, 26, 0, tzinfo=UTC)
    # Land cells carry no waves: next to Grand Bahama the nearest sea cell is used.
    assert p.values["points"]["w27n078w"]["method"] == "nearest"
    assert len(p.values["points"]) == len(pts)


def test_wave_steps() -> None:
    run = datetime(2026, 9, 26, 0, tzinfo=UTC)
    assert nomads.wave_lead(run, datetime(2026, 9, 27, 5, 40, tzinfo=UTC)) == 30
    assert nomads.wave_lead(run, datetime(2026, 10, 3, 1, tzinfo=UTC)) == 168  # 3-hourly
    assert nomads.wave_lead(run, datetime(2026, 9, 25, tzinfo=UTC)) is None


def test_grib_split_refuses_a_truncated_message() -> None:
    from app.feeds.parsers import grib

    body = raw("hrrr_f06_subset.grb2")
    with pytest.raises(ParseError, match="truncated"):
        grib.split_messages(body[:-10])
    assert len(grib.split_messages(body)) == 5


def test_grib_bilinear_is_exact_for_a_linear_field() -> None:
    from app.feeds.parsers.grib import _bilinear

    near = [
        {"lat": 28.5, "lon": 279.5, "value": 1.0, "distance": 1},
        {"lat": 28.5, "lon": 280.0, "value": 3.0, "distance": 1},
        {"lat": 29.0, "lon": 279.5, "value": 5.0, "distance": 1},
        {"lat": 29.0, "lon": 280.0, "value": 7.0, "distance": 1},
    ]
    # value = 1 + 4*(lon-279.5) + 8*(lat-28.5)
    assert _bilinear(near, 28.75, -80.25) == pytest.approx(1 + 4 * 0.25 + 8 * 0.25)
