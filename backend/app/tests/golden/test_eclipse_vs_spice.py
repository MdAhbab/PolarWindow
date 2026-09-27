"""Shadow edges along IM-2's flown trip against SPICE's own occultation finder (gfoclt).

Acceptance (plan, T2 eclipse): every edge within 1 s of ``gfoclt`` with the
same spheres. Both sides use light time only (gfoclt has no stellar
aberration), the Moon's PCK radius and the same Sun radius.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.config import get_settings

pytestmark = [pytest.mark.requires_kernels, pytest.mark.requires_clps_spice, pytest.mark.slow]

SPK = "clps/clps_prime1_im2_cru_rec_250227_250306_v01.bsp"
SC = "-370021"


@pytest.fixture(scope="module")
def loaded():
    from app.core import spice

    s = get_settings()
    path = s.data_dir / SPK
    if not path.exists():
        pytest.skip(f"{SPK} not on disk (polar-data sync)")
    spice.load(s.kernel_dir)
    spice.load_extra([path])
    return spice


def test_moon_shadow_edges_match_gfoclt_to_a_second(loaded) -> None:
    import spiceypy as sp

    from app.core import eclipse, intervals

    spice = loaded
    # Two days of lunar orbit before landing.
    a = spice.utc_to_et("2025-03-04T00:00:00")
    b = spice.utc_to_et("2025-03-06T00:00:00")
    r_moon_km = float(np.asarray(sp.bodvrd("MOON", "RADII", 3)[1])[0])
    r_sun_km = float(np.asarray(sp.bodvrd("SUN", "RADII", 3)[1])[0])

    ets = np.arange(a, b + 1.0, 60.0)
    t = ets - a
    to_sun = spice.positions("SUN", SC, "J2000", "LT", ets, knot_s=None)
    to_moon = spice.positions("MOON", SC, "J2000", "LT", ets, knot_s=None)
    occ = eclipse.occultation(to_sun, to_moon, r_sun_km * 1000.0, r_moon_km * 1000.0)
    ours = [r for r in eclipse.shadow_runs(t, [occ]) if r.value]

    cnfine = sp.cell_double(2)
    sp.wninsd(a, b, cnfine)
    result = sp.cell_double(2000)
    sp.gfoclt(
        "ANY",
        "MOON",
        "ELLIPSOID",
        "IAU_MOON",
        "SUN",
        "ELLIPSOID",
        "IAU_SUN",
        "LT",
        SC,
        30.0,
        cnfine,
        result,
    )
    theirs = [sp.wnfetd(result, i) for i in range(sp.wncard(result))]
    assert len(theirs) >= 10, "expected many shadow passes in low lunar orbit"
    assert len(ours) == len(theirs)
    worst = 0.0
    for r, (s0, s1) in zip(ours, theirs, strict=True):
        worst = max(worst, abs(r.start - (s0 - a)), abs(r.end - (s1 - a)))
    assert worst < 1.0, f"worst edge differs by {worst:.3f} s"
    assert intervals.EPS_S < 1.0
