"""The cited catalogues load, cross-reference, and say where each value came from."""

from __future__ import annotations

import json

import pytest

from app.config import get_settings
from app.data import catalogues


def test_every_catalogue_loads_and_its_references_resolve() -> None:
    for name in catalogues.CATALOGUES:
        assert catalogues.load(name).records, name
    assert catalogues.check_references() == []


def test_weather_rules_are_verbatim_and_classified() -> None:
    rules = catalogues.load("weather_rules")
    wind = rules.get("f9-wind-162ft")
    assert wind.text.startswith("Do not launch if the sustained wind at the 162-foot level")
    assert (wind.threshold, wind.unit, wind.comparison) == (30.0, "mph", "gt")
    assert wind.height_m == pytest.approx(162 * 0.3048, abs=0.01)
    assert wind.provenance("applies_to")[0] == "assumed"
    assert {r.rule_class for r in rules.records} == {"model", "proxy", "observation"}
    shear = rules.get("f9-upper-wind-shear")
    assert shear.threshold is None and "threshold" in shear.unconfirmed_fields


def test_recovery_zones_name_flown_missions() -> None:
    ids = {
        m["id"]
        for m in json.loads((get_settings().data_dir / "missions.json").read_text())["missions"]
    }
    zones = catalogues.load("recovery_zones")
    for z in zones.records:
        assert set(z.used_by) <= ids
    assert zones.get("asog").downrange_km == 700.0 and zones.get("asog").lat_deg is None
    assert zones.get("lz-1").lat_deg == pytest.approx(28.4857, abs=1e-3)


def test_a_zone_without_a_source_for_its_kind_is_refused() -> None:
    raw = json.loads(catalogues.path_of("recovery_zones").read_bytes())
    del raw["records"][0]["field_sources"]["kind"]
    with pytest.raises(catalogues.CatalogueError, match="kind"):
        catalogues.parse("recovery_zones", json.dumps(raw).encode())
