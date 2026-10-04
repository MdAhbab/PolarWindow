"""M10: counts the report quotes (missions, catalogues, feeds, datasets, ADRs, contracts).

Run from backend/: uv run python ../docs/report/scripts/counts.py
"""
from __future__ import annotations

import json
import re
import subprocess
import tomllib
from collections import Counter
from pathlib import Path

import httpx

R = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "out" / "counts.json"
OUT.parent.mkdir(exist_ok=True)

m = json.loads((R / "data/missions.json").read_text())
ms = m["missions"]
payloads = [p for x in ms for p in x["payloads"]]
res: dict = {
    "head": subprocess.check_output(["git", "-C", str(R), "rev-parse", "--short", "HEAD"], text=True).strip(),
    "missions": {
        "schema_version": m["schema_version"],
        "compiled": m.get("compiled"),
        "n": len(ms),
        "status": Counter(x["status"] for x in ms),
        "payloads": len(payloads),
        "payloads_with_source_url": sum(1 for p in payloads if p.get("source_url")),
        "unconfirmed_fields": sum(len(x.get("unconfirmed_fields") or []) for x in ms)
        + sum(len(p.get("unconfirmed") or []) for p in payloads),
        "with_target": sum(1 for x in ms if x.get("target")),
        "with_t0": sum(1 for x in ms if x.get("t0")),
        "with_vehicle": sum(1 for x in ms if x.get("vehicle_id")),
        "with_rovers": sum(1 for x in ms if x.get("rovers")),
        "returns": Counter(str(x.get("returns")) for x in ms),
        "transfer_types": Counter(str((x.get("transfer") or {}).get("type")) for x in ms),
        "source_entries": sum(len(x.get("sources") or []) for x in ms),
    },
    "catalogues": {},
}
for f in sorted((R / "data/catalogues").glob("*.json")):
    d = json.loads(f.read_text())
    recs = d.get("records") or d.get("scales") or []
    row = {"records": len(recs), "compiled": d.get("compiled")}
    if f.stem == "weather_rules":
        row["classes"] = Counter(r["rule_class"] for r in recs)
    if f.stem == "relays":
        row["status"] = Counter(str(r.get("status")) for r in recs)
    if f.stem == "ground_stations":
        row["operators"] = Counter(str(r.get("operator")) for r in recs)
    if f.stem == "landing_attempts":
        row["outcomes"] = Counter(str(r.get("outcome")) for r in recs)
    res["catalogues"][f.stem] = row

feeds = httpx.get("http://localhost:8000/api/v1/feeds", timeout=20).json()["feeds"]
res["feeds"] = {
    "products": len(feeds),
    "providers": sorted({f["provider"] for f in feeds}),
    "stale": sum(1 for f in feeds if f["stale"]),
    "failing_breaker_open": sum(1 for f in feeds if f.get("breaker") not in (None, "closed")),
    "licences": Counter(str(f.get("licence")) for f in feeds),
}
res["healthz"] = httpx.get("http://localhost:8000/healthz", timeout=20).json()

from app.data.registry import DATASETS  # noqa: E402

res["registry"] = {"datasets": len(DATASETS), "tiers": Counter(str(d.tier) for d in DATASETS)}
res["adrs"] = len(list((R / "docs/adr").glob("0*.md")))
conv = (R / "docs/conventions.md").read_text()
res["invariants"] = sorted({int(n) for n in re.findall(r"^\s*(\d+)\.\s+\*\*", conv, re.M)})
pp = tomllib.loads((R / "backend/pyproject.toml").read_text())
res["import_contracts"] = len(pp["tool"]["importlinter"]["contracts"])
res["core_modules"] = len([p for p in (R / "backend/app/core").glob("*.py") if p.name != "__init__.py"])
routes = json.loads((R / "docs/openapi.json").read_text())["paths"]
res["api_paths"] = len(routes)
res["api_operations"] = sum(len([k for k in v if k in ("get", "post", "put", "patch", "delete")]) for v in routes.values())
OUT.write_text(json.dumps(res, indent=1, default=str) + "\n")
print(json.dumps(res, default=str)[:3000])
