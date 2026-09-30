"""Build ``data/catalogues/ground_stations.json`` from the DSN's own files.

``python -m app.data.build_ground_stations`` reads:

* the DSN Telecommunications Link Design Handbook 810-005, module 301,
  revision O: ``Horizon-Masks-Download-V2-301O.xlsx`` (receive, low-power and
  high-power transmit elevation limits per antenna, every degree of azimuth,
  effective 1 May 2024). Only the receive mask is used: a lander is *heard*
  when the Moon is above it.
* Table 5 of the same module (geodetic coordinates on WGS 84), transcribed
  below exactly as printed, for display. Computations use the NAIF DSN
  station kernel (``earthstns_itrf93_*.bsp``), not these numbers.

The spreadsheet is read with the standard library (it is a zip of XML), so
no spreadsheet package is needed.
"""

from __future__ import annotations

import json
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from defusedxml import ElementTree

from app.config import get_settings

XLSX = "Horizon-Masks-Download-V2-301O.xlsx"
XLSX_URL = "https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/Horizon-Masks-Download-V2-301O.xlsx"
PDF_URL = "https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301O.pdf"

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

#: 810-005 module 301 Rev. O, Table 5: latitude and longitude (deg, min, sec;
#: longitude east) and height above the WGS 84 ellipsoid (m). "For southern
#: hemisphere antennas deg, min, sec should all be treated as negative."
TABLE_5: dict[str, tuple[tuple[int, int, float], tuple[int, int, float], float]] = {
    "DSS-14": ((35, 25, 33.24312), (243, 6, 37.66244), 1001.390),
    "DSS-24": ((35, 20, 23.61416), (243, 7, 30.74007), 951.499),
    "DSS-25": ((35, 20, 15.40306), (243, 7, 28.69246), 959.634),
    "DSS-26": ((35, 20, 8.48118), (243, 7, 37.14062), 968.686),
    "DSS-34": ((-35, -23, -54.52383), (148, 58, 55.07191), 692.020),
    "DSS-35": ((-35, -23, -44.86387), (148, 58, 53.24088), 694.897),
    "DSS-36": ((-35, -23, -42.36634), (148, 58, 42.75912), 685.503),
    "DSS-43": ((-35, -24, -8.72724), (148, 58, 52.56231), 688.867),
    "DSS-53": ((40, 25, 37.50154), (355, 44, 47.74405), 842.806),
    "DSS-54": ((40, 25, 32.23805), (355, 44, 45.25141), 837.051),
    "DSS-55": ((40, 25, 27.46525), (355, 44, 50.52012), 819.061),
    "DSS-56": ((40, 25, 33.47285), (355, 44, 52.58149), 835.746),
    "DSS-63": ((40, 25, 52.35510), (355, 45, 7.16924), 864.816),
    "DSS-65": ((40, 25, 37.94289), (355, 44, 57.48397), 833.854),
}

COMPLEX = {
    "DSS-1": "Goldstone, California (GDSCC)",
    "DSS-2": "Goldstone, California (GDSCC)",
    "DSS-3": "Canberra, Australia (CDSCC)",
    "DSS-4": "Canberra, Australia (CDSCC)",
    "DSS-5": "Madrid, Spain (MDSCC)",
    "DSS-6": "Madrid, Spain (MDSCC)",
}


def _deg(d: tuple[int, int, float]) -> float:
    return d[0] + d[1] / 60.0 + d[2] / 3600.0


def read_masks(path: Path) -> dict[str, dict[str, Any]]:
    """``{antenna: {"kind": "34-m BWG", "rcv": [360 elevations], "note": ...}}``."""
    z = zipfile.ZipFile(path)
    ss = [
        "".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t"))
        for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS)
    ]
    rels = z.read("xl/_rels/workbook.xml.rels").decode()
    rid = {m.group(1): m.group(2) for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels)}
    rid |= {
        m.group(2): m.group(1) for m in re.finditer(r'Target="([^"]+)"[^>]*Id="(rId\d+)"', rels)
    }
    out: dict[str, dict[str, Any]] = {}
    for sh in ElementTree.fromstring(z.read("xl/workbook.xml")).iter(f"{{{_NS['m']}}}sheet"):
        name = sh.get("name")
        if not name or not name.startswith("DSS-"):
            continue
        root = ElementTree.fromstring(z.read("xl/" + rid[sh.get(_R)]))
        cells: dict[str, str] = {}
        for c in root.iter(f"{{{_NS['m']}}}c"):
            v = c.find("m:v", _NS)
            if v is not None and v.text is not None:
                cells[str(c.get("r"))] = ss[int(v.text)] if c.get("t") == "s" else v.text
        if cells.get("C10") != "AZIM" or cells.get("D10") != "RCV":
            raise ValueError(f"{name}: the mask table is not where 301O puts it (C10/D10)")
        rcv = []
        for i in range(11, 371):
            az = int(float(cells[f"C{i}"]))
            if az != i - 11:
                raise ValueError(f"{name}: azimuth rows are not 0..359 in one-degree steps")
            rcv.append(round(float(cells[f"D{i}"]), 3))
        notes = [cells[k] for k in ("J2", "J7", "E5") if cells.get(k)]
        out[name] = {"kind": cells.get("A2", ""), "rcv": rcv, "notes": notes}
    return out


def build(dsn_dir: Path, accessed: str) -> dict[str, Any]:
    masks = read_masks(dsn_dir / XLSX)
    xlsx_src = {
        "url": XLSX_URL,
        "title": "DSN 810-005 module 301 Rev. O horizon mask download spreadsheet "
        "(masks effective 1 May 2024)",
        "publisher": "NASA JPL Deep Space Network",
        "accessed": accessed,
    }
    pdf_src = {
        "url": PDF_URL,
        "title": "DSN Telecommunications Link Design Handbook 810-005, module 301 Rev. O, "
        "Coverage and Geometry (Table 5, geodetic coordinates)",
        "publisher": "NASA JPL Deep Space Network",
        "accessed": accessed,
    }
    recs = []
    for name, m in masks.items():
        if name not in TABLE_5:
            continue  # DSS-23 and DSS-33 are future antennas at estimated locations
        lat, lon, h = TABLE_5[name]
        lon_e = _deg(lon)
        recs.append(
            {
                "id": name.lower(),
                "name": f"{name} ({m['kind']})",
                "network": "DSN",
                "operator": "NASA JPL",
                "lat_deg": round(_deg(lat), 9),
                "lon_deg": round(lon_e - 360.0 if lon_e > 180 else lon_e, 9),
                "height_m": h,
                "naif_name": name,
                "diameter_m": 70.0 if m["kind"].startswith("70") else 34.0,
                "bands": [],
                "mask": [{"az_deg": float(az), "el_deg": el} for az, el in enumerate(m["rcv"])],
                "min_elevation_deg": min(m["rcv"]),
                "status": "operating",
                "sources": [pdf_src, xlsx_src],
                "field_sources": {
                    "network": pdf_src["url"],
                    "operator": pdf_src["url"],
                    "lat_deg": pdf_src["url"],
                    "lon_deg": pdf_src["url"],
                    "height_m": pdf_src["url"],
                    "naif_name": pdf_src["url"],
                    "diameter_m": pdf_src["url"],
                    "mask": xlsx_src["url"],
                    "min_elevation_deg": xlsx_src["url"],
                    "status": xlsx_src["url"],
                },
                "assumed_fields": {},
                "unconfirmed_fields": ["bands"],
                "notes": [
                    f"{COMPLEX.get(name[:5], '')}. Receive mask: the lowest elevation the "
                    "antenna can track at each degree of azimuth (terrain, neighbouring "
                    "antennas, or the mechanical limit)."
                ]
                + m["notes"],
            }
        )
    return {
        "schema_version": 1,
        "catalogue": "ground_stations",
        "compiled": accessed,
        "about": "Deep Space Network antennas with their published receive horizon masks "
        "(810-005 module 301 Rev. O). Other networks' stations are not listed yet: their "
        "masks are not published, so any added later carry an assumed flat limit, labelled.",
        "records": recs,
    }


def main() -> None:
    s = get_settings()
    out = build(s.data_dir / "dsn", date.today().isoformat())
    path = s.data_dir / "catalogues" / "ground_stations.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path}: {len(out['records'])} antennas")


if __name__ == "__main__":
    main()
