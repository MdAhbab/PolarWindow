"""The droneship zone and the sea there (T4 B2), without the database."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.feeds.adapters import nomads
from app.services import return_service as rs

FX = Path(__file__).resolve().parents[1] / "fixtures" / "feeds"


def test_destination_and_distance_agree() -> None:
    lat, lon = rs.destination(28.6082, -80.6043, 90.0, 700.0)
    # A great circle leaving due east bends towards the equator.
    assert lat == pytest.approx(28.42, abs=0.01) and lon == pytest.approx(-73.44, abs=0.01)
    assert rs.distance_km((28.6082, -80.6043), (lat, lon)) == pytest.approx(700.0, abs=1e-6)
    # Due north a degree is 111.2 km on this sphere.
    assert rs.destination(0.0, 10.0, 0.0, 111.195)[0] == pytest.approx(1.0, abs=1e-4)


def test_sea_at_the_nearest_lattice_point_and_step() -> None:
    p = nomads.parse_points(nomads.wave_points("florida"), "GFS-Wave", 1)(
        (FX / "gfswave_florida_f024.grb2").read_bytes()
    )
    zone = rs.destination(28.6082, -80.6043, 90.0, 700.0)
    got = rs.sea_at(p.values, zone, datetime(2026, 9, 27, 0, 30, tzinfo=UTC))
    assert got is not None
    fields, d_km, valid = got
    assert d_km < rs.LATTICE_WITHIN_KM and valid == datetime(2026, 9, 27, tzinfo=UTC)
    assert fields["wave_height_m"] > 0.0
    # Two hours from the only step recorded: no forecast for that time.
    assert rs.sea_at(p.values, zone, datetime(2026, 9, 27, 2, 0, tzinfo=UTC)) is None
    # Far outside the lattice: nothing.
    assert rs.sea_at(p.values, (10.0, -40.0), datetime(2026, 9, 27, tzinfo=UTC)) is None


def test_imported_marine_wave_retains_independent_noaa_wind_and_source():
    when = datetime(2026, 10, 1, tzinfo=UTC)
    sea = {"wind_m_s": {"value": 7., "source": "NOAA"}, "wave_height_m": {"value": 3.},
           "note": "NOAA sea", "times": [when], "sources": [{"name": "NOAA"}]}
    marine = {"valid": when, "distance_km": 2., "wave_height_m": 1.5,
              "imported_at": when, "source_url": "https://example.test/waves"}
    result = rs._with_marine(sea, marine)
    assert result["wave_height_m"]["value"] == 1.5
    assert result["wind_m_s"] == {"value": 7., "source": "NOAA"}
    assert len(result["sources"]) == 2
    assert "issuance time is not provided" in result["wave_height_m"]["no_margin_reason"]
