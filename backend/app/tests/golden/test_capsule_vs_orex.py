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


def test_the_days_air_lands_it_where_docs_validation_says_which_is_over_the_10_km(
    entry_state,
) -> None:
    """The air of the entry day, NRLMSISE-00 driven by that day's solar flux and geomagnetic
    activity, is what the service flies through when the OMNI files have the day. The plan's
    10 km is not met with it (docs/validation.md, capsule entry): this pins the result that
    is recorded there, so that a change of the air or of the model shows up here first."""
    from app.core import entry
    from app.services import capsule
    from app.tests.golden import validate_capsule as v

    et0, r0, v0 = entry_state
    atm = capsule.day_atmosphere(et0)
    if atm.air is None:
        pytest.skip(atm.fallback_reason or "no solar flux and ap for the entry day")
    ld = capsule.land(et0, r0, v0, entry.Capsule(v.beta(sum(v.CA) / 2), air=atm.air), v.TOUCHDOWN_M)
    assert ld.landed
    d = capsule.distance_km(ld.lat_deg, ld.lon_deg, *v.MEASURED)
    assert d == pytest.approx(12.1, abs=0.3)
    assert d > v.LIMIT_KM
