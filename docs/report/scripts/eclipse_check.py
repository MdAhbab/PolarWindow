"""Shadow edges along IM-2's lunar orbit against SPICE gfoclt: count and worst difference.

Same computation as backend/app/tests/golden/test_eclipse_vs_spice.py, printed instead of
asserted. Run from backend/: uv run python ../docs/report/scripts/eclipse_check.py
"""
import json
from pathlib import Path

import numpy as np
import spiceypy as sp

from app.config import get_settings
from app.core import eclipse, spice

SPK = "clps/clps_prime1_im2_cru_rec_250227_250306_v01.bsp"
SC = "-370021"
s = get_settings()
spice.load(s.kernel_dir)
spice.load_extra([s.data_dir / SPK])
a = spice.utc_to_et("2025-03-04T00:00:00")
b = spice.utc_to_et("2025-03-06T00:00:00")
r_moon = float(np.asarray(sp.bodvrd("MOON", "RADII", 3)[1])[0]) * 1000.0
r_sun = float(np.asarray(sp.bodvrd("SUN", "RADII", 3)[1])[0]) * 1000.0
ets = np.arange(a, b + 1.0, 60.0)
t = ets - a
occ = eclipse.occultation(
    spice.positions("SUN", SC, "J2000", "LT", ets, knot_s=None),
    spice.positions("MOON", SC, "J2000", "LT", ets, knot_s=None), r_sun, r_moon)
ours = [r for r in eclipse.shadow_runs(t, [occ]) if r.value]
cn = sp.cell_double(2); sp.wninsd(a, b, cn); res = sp.cell_double(2000)
sp.gfoclt("ANY", "MOON", "ELLIPSOID", "IAU_MOON", "SUN", "ELLIPSOID", "IAU_SUN", "LT", SC, 30.0, cn, res)
theirs = [sp.wnfetd(res, i) for i in range(sp.wncard(res))]
diffs = [d for r, (s0, s1) in zip(ours, theirs, strict=True) for d in (abs(r.start - (s0 - a)), abs(r.end - (s1 - a)))]
out = {"passes_ours": len(ours), "passes_spice": len(theirs), "edges": len(diffs),
       "worst_s": max(diffs), "median_s": float(np.median(diffs)), "window": "2025-03-04 to 2025-03-06, IM-2 lunar orbit, 60 s step"}
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
(OUT / "eclipse_check.json").write_text(json.dumps(out, indent=1) + "\n")
print(out)
