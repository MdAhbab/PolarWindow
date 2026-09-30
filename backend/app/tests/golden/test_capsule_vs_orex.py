"""The capsule entry model against OSIRIS-REx's landing (plan track H: within 10 km).

The full tables and the footprint are ``make validate-capsule``; this checks the
acceptance in the standard atmosphere, the recorded result in the day's air, and the entry
state, in a few seconds.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.requires_kernels]


@pytest.fixture(scope="module")
def entry_state():
    from app.config import get_settings
    from app.core import spice
    from app.data import registry
    from app.tests.golden import validate_capsule

    spk = get_settings().data_dir / registry.by_id("naif:orex-src-entry").dest
    if not spk.exists():
        pytest.skip("OSIRIS-REx capsule SPK not on disk (polar-data sync)")
    spice.load(get_settings().kernel_dir)
    return validate_capsule._entry()


def test_the_entry_state_is_the_published_one(entry_state) -> None:
    from app.services import capsule
    from app.tests.golden import validate_capsule

    got = capsule.entry_state(entry_state[1], entry_state[2], entry_state[0])
    for k, v in validate_capsule.PUBLISHED.items():
        assert got[k] == pytest.approx(v, abs=2e-3), k


def test_the_capsule_lands_within_10_km_of_where_it_did_in_the_standard_atmosphere(
    entry_state,
) -> None:
    from app.core import entry
    from app.services import capsule
    from app.tests.golden import validate_capsule as v

    et0, r0, v0 = entry_state
    b = v.beta(sum(v.CA) / 2)
    ld = capsule.land(et0, r0, v0, entry.Capsule(b), v.TOUCHDOWN_M)
    assert ld.landed
    assert capsule.distance_km(ld.lat_deg, ld.lon_deg, *v.MEASURED) <= v.LIMIT_KM


def _landing_km(entry_state, model: str, ca: float) -> float:
    from app.core import entry
    from app.services import capsule
    from app.tests.golden import validate_capsule as v

    et0, r0, v0 = entry_state
    atm = capsule.day_atmosphere(et0, model)
    if atm.air is None:
        pytest.skip(atm.fallback_reason or "no solar flux and ap for the entry day")
    ld = capsule.land(et0, r0, v0, entry.Capsule(v.beta(ca), air=atm.air), v.TOUCHDOWN_M)
    assert ld.landed
    return capsule.distance_km(ld.lat_deg, ld.lon_deg, *v.MEASURED)


def test_the_days_air_lands_it_where_docs_validation_says_which_is_inside_the_10_km(
    entry_state,
) -> None:
    """The air of the entry day, NRLMSIS 2.1 driven by that day's solar flux and geomagnetic
    activity (the model that came nearest to measured air between 30 and 70 km,
    ``golden.capsule_air``), is what the service flies through when the OMNI files have the
    day. The plan's 10 km is met with it, over the whole published drag range (docs/validation.md,
    capsule entry): this pins the result recorded there, so that a change of the air or of the
    model shows up here first."""
    from app.services import capsule
    from app.tests.golden import validate_capsule as v

    assert capsule.DEFAULT_MODEL == "NRLMSIS 2.1"
    middle = _landing_km(entry_state, capsule.DEFAULT_MODEL, sum(v.CA) / 2)
    assert middle == pytest.approx(6.6, abs=0.3)
    ends = [_landing_km(entry_state, capsule.DEFAULT_MODEL, ca) for ca in v.CA]
    assert ends == pytest.approx([3.9, 9.3], abs=0.3)
    assert max(middle, *ends) <= v.LIMIT_KM


def test_the_older_model_flown_for_comparison_lands_where_it_did_over_the_limit(
    entry_state,
) -> None:
    """NRLMSISE-00 is 4 to 7 % too dense at 45 to 70 km against measured air, and lands the
    capsule 12.1 km from the measured point: it is recorded, not used."""
    from app.tests.golden import validate_capsule as v

    d = _landing_km(entry_state, "NRLMSISE-00", sum(v.CA) / 2)
    assert d == pytest.approx(12.1, abs=0.3)
    assert d > v.LIMIT_KM
