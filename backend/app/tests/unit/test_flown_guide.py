"""The launch vehicles' published injection accuracy as the correction budget takes it:
what the catalogue holds (``vehicles.json``), which row a vehicle gives
(``flown_burns.guide_for``) and how the errors behind a budget are put in words."""

from __future__ import annotations

import math

import numpy as np

from app.core import lincov
from app.data import catalogues
from app.services import flown_burns

MU = 3.986004354360959e14
R_EARTH = 6_378_136.6


def _plan_state() -> np.ndarray:
    rp, ra = R_EARTH + 300e3, 3.9e8
    return np.array([rp, 0.0, 0.0, 0.0, math.sqrt(2.0 * MU * ra / (rp * (ra + rp))), 0.0])


def test_every_published_row_names_its_guide_page_and_how_many_deviations_it_is() -> None:
    cat = catalogues.load("vehicles")
    with_rows = [v for v in cat.records if v.injection_accuracy]
    assert {v.id for v in with_rows} == {"falcon-9", "vulcan-centaur", "new-glenn"}
    for v in with_rows:
        url = v.field_sources["injection_accuracy"]
        source = next(s for s in v.sources if s.url == url)
        assert "#page=" in url and "page" in source.title and "Table" in source.title, v.id
        assert "SHA-256" in source.title  # the copy that was read, so the citation can be checked
        for r in v.injection_accuracy:
            assert "Table" in r.cited and "page" in r.cited and "'" not in r.cited
            assert r.perigee_pm_km or r.apogee_pm_km or r.inclination_pm_deg
        # The number of standard deviations: printed in the guide, or an assumed range.
        if "injection_sigma" in v.assumed_fields:
            a = v.assumed_fields["injection_sigma"]
            assert a.lo is not None and a.hi is not None and a.lo <= v.injection_sigma <= a.hi
        else:
            assert v.field_sources["injection_sigma"] == url and v.injection_sigma == 3.0


def test_a_vehicle_whose_guide_prints_nothing_has_nothing_entered() -> None:
    fh = catalogues.load("vehicles").get("falcon-heavy")
    assert fh.injection_accuracy == [] and fh.injection_sigma is None
    assert {"injection_accuracy", "injection_sigma"} <= set(fh.unconfirmed_fields)
    assert flown_burns.guide_for("falcon-heavy") is None
    assert flown_burns.guide_for(None) is None


def test_falcon_9_gives_the_geosynchronous_transfer_row_of_its_2015_guide() -> None:
    g = flown_burns.guide_for("falcon-9")
    assert g is not None
    assert g.vehicle == "Falcon 9 Block 5" and not g.sigma_assumed
    assert g.orbit == "Geosynchronous transfer orbit (185 km x 35,786 km)"
    assert "Rev 2" in g.cited and "Table 3-2, page 16" in g.cited
    assert g.row == lincov.GuideRow(185.0, 35_786.0, 10.0, 500.0, 0.1, 3.0)


def test_vulcan_gives_its_lunar_transfer_row_and_says_its_deviations_are_assumed() -> None:
    g = flown_burns.guide_for("vulcan-centaur")
    assert g is not None and g.sigma_assumed
    assert g.orbit == "Lunar Transfer/Earth Escape"
    assert g.row == lincov.GuideRow(None, None, 1.9, 4630.0, 0.01, 3.0)
    assert "Table 2.3-1, page 2-9" in g.cited


def test_new_glenn_gives_its_geosynchronous_transfer_row() -> None:
    g = flown_burns.guide_for("new-glenn")
    assert g is not None and not g.sigma_assumed
    assert g.row == lincov.GuideRow(185.0, 35_786.0, 7.4, 200.0, 0.05, 3.0)
    assert "Table 2-3, page 31" in g.cited


def _words(vehicle: str) -> list[flown_burns.Input]:
    g = flown_burns.guide_for(vehicle)
    assert g is not None
    errors, found = lincov.from_guide(flown_burns.ASSUMED, g.row, _plan_state(), MU, R_EARTH)
    return flown_burns.input_words(errors, found, g)


def test_the_words_for_falcon_9_say_which_three_errors_are_published_and_from_where() -> None:
    rows = _words("falcon-9")
    published = {r.what: r for r in rows if r.basis == "published"}
    assert set(published) == {
        "Leaving Earth, position up or down",
        "Leaving Earth, speed along the path",
        "Leaving Earth, speed sideways",
    }
    assert published["Leaving Earth, position up or down"].value == "3.3 km"
    assert published["Leaving Earth, speed along the path"].value == "2.7 m/s"
    assert published["Leaving Earth, speed sideways"].value == "6.0 m/s"
    for r in published.values():
        assert r.source is not None and "Table 3-2, page 16" in r.source
        assert "three standard deviations" in r.source and "does not say" not in r.source
    assumed = [r for r in rows if r.basis == "assumed"]
    assert all(r.source is None for r in assumed)
    assert {r.what for r in assumed} == {
        "Leaving Earth, position along the path and sideways",
        "Leaving Earth, speed up or down",
        "Where the team thinks the lander is, at each correction",
        "How well a burn fires",
    }
    # One row a name (the screen keys on it), and plain words with no straight apostrophe.
    names = [r.what for r in rows]
    assert len(names) == len(set(names))
    for r in rows:
        assert "'" not in r.what + r.value + (r.source or "")


def test_the_words_for_vulcan_say_the_deviations_are_a_guess() -> None:
    rows = _words("vulcan-centaur")
    published = [r for r in rows if r.basis == "published"]
    assert len(published) == 3
    for r in published:
        assert r.source is not None and "does not say how many standard deviations" in r.source


def test_with_no_guide_every_error_is_assumed_in_the_words_it_always_had() -> None:
    rows = flown_burns.input_words(flown_burns.ASSUMED, [], None)
    assert [(r.what, r.value) for r in rows] == list(flown_burns.ASSUMED_WORDS)
    assert {r.basis for r in rows} == {"assumed"} and {r.source for r in rows} == {None}
