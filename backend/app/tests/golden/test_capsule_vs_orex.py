"""The capsule entry model against OSIRIS-REx's landing (plan track H: within 10 km).

The full tables and the footprint are ``make validate-capsule``; this checks the
acceptance and the entry state, in under a second.
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


def test_the_capsule_lands_within_10_km_of_where_it_did(entry_state) -> None:
    from app.core import entry
    from app.services import capsule
    from app.tests.golden import validate_capsule as v

    et0, r0, v0 = entry_state
    b = v.beta(sum(v.CA) / 2)
    ld = capsule.land(et0, r0, v0, entry.Capsule(b), v.TOUCHDOWN_M)
    assert ld.landed
    assert capsule.distance_km(ld.lat_deg, ld.lon_deg, *v.MEASURED) <= v.LIMIT_KM
