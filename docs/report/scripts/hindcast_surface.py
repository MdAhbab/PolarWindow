"""Landing hindcast: the first computed sunset after touchdown at each flown lander's published
point, with its margin and the terrain coverage, from GET /sites/{id}/windows (300 s step)."""
import json
from pathlib import Path
import httpx
API = "http://127.0.0.1:8000/api/v1"
CASES = {  # mission: (window start, window end); the published surface windows start at touchdown
    "blue-ghost-m1": ("2025-03-02T09:00:00Z", "2025-03-18T00:00:00Z"),
    "im-1": ("2024-02-22T23:23:00Z", "2024-03-10T00:00:00Z"),
    "im-2": ("2025-03-06T17:30:00Z", "2025-03-26T00:00:00Z"),
}
out = {}
with httpx.Client(timeout=120) as c:
    for mid, (a, b) in CASES.items():
        m = c.get(f"{API}/missions/{mid}").json()
        sid = m["site_id"]
        w = c.get(f"{API}/sites/{sid}/windows", params={"start": a, "end": b, "step_s": 300}).json()
        sun = w["sun"]["arcs"]; earth = w["earth"]["arcs"]
        first_set = next((x for x in sun if x["up"] and not x["open_end"]), None)
        unc = w["meta"]["uncertainty"]
        out[mid] = {"site_id": sid, "surface_window": m["surface_window"], "window": [a, b],
                    "first_sunset": first_set and first_set["end"],
                    "sunset_tolerance_min": first_set and first_set["end_tolerance_s"] and round(first_set["end_tolerance_s"] / 60, 1),
                    "earth_first_set": next((x["end"] for x in earth if x["up"] and not x["open_end"]), None),
                    "terrain_modelled": unc.get("terrain_modelled"), "coverage": unc.get("coverage"),
                    "dem_vertical_error_m": unc.get("dem_vertical_error_m")}
        print(mid, out[mid])
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
(OUT / "hindcast_surface.json").write_text(json.dumps(out, indent=1) + "\n")
