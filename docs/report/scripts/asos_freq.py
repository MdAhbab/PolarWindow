"""How often the Cape's station (ASOS KXMR) reported a 10 m sustained wind above the hindcast's
threshold (10.52 m/s, 23.5 mph): 2025 and 2015-2024. Reads the file make hindcast-weather cached."""
import csv, json
from pathlib import Path
THR = 10.51944399731159
KT = 1852.0 / 3600.0
ROOT = Path(__file__).resolve().parents[3]
rows = list(csv.DictReader(open(ROOT / "data" / "hindcast" / "asos_XMR_2015_2025.csv")))
def freq(y0, y1):
    v = [float(r["sknt"]) * KT for r in rows if r["sknt"] not in ("", "M") and y0 <= int(r["valid"][:4]) <= y1]
    k = sum(1 for x in v if x > THR)
    return {"reports": len(v), "above": k, "percent": round(100 * k / len(v), 2)}
out = {"threshold_m_s": THR, "2025": freq(2025, 2025), "2015-2024": freq(2015, 2024)}
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
(OUT / "asos_freq.json").write_text(json.dumps(out, indent=1) + "\n")
print(out)
