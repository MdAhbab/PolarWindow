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


M101_URL = "https://deepspace.jpl.nasa.gov/dsndocs/810-005/101/101I.pdf"
M104_URL = "https://deepspace.jpl.nasa.gov/dsndocs/810-005/104/104O.pdf"
M105_URL = "https://deepspace.jpl.nasa.gov/dsndocs/810-005/105/105E.pdf"

#: 810-005 module 101 Rev. I: 70-m X-band receive, X-only configuration (S/X dichroic
#: retracted), 8420 MHz. Gain from Table 2 (+/- 0.1 dBi); T_AMW from Table 4 (+/- 1 K).
RX_70M: dict[str, tuple[float, float]] = {
    "DSS-14": (74.55, 11.65),
    "DSS-43": (74.63, 12.10),
    "DSS-63": (74.66, 11.46),
}
#: Module 104 Rev. O Table 9: 34-m BWG X/Ka-mode, HEMT-1 (RCP), gain 68.32 +0.1/-0.2 dBi at
#: 8425 MHz (one value for these antennas); T_AMW per antenna, -1.0/+2.0 K. DSS-24 (maser,
#: several paths) and DSS-65 (not in module 104) are not taken.
RX_34M_TAMW: dict[str, float] = {
    "DSS-25": 16.2,
    "DSS-26": 16.29,
    "DSS-34": 16.28,
    "DSS-35": 14.7,
    "DSS-36": 12.59,
    "DSS-53": 13.1,
    "DSS-54": 18.31,
    "DSS-55": 17.42,
    "DSS-56": 14.47,
}
#: Module 105 Rev. E Tables 13-15, year-average column: zenith attenuation at X-band, dB,
#: at cumulative distribution 25 % and 99 %.
ATM_X: dict[str, tuple[str, float, float, str]] = {
    "DSS-1": ("Goldstone", 0.039, 0.070, "Table 13"),
    "DSS-2": ("Canberra", 0.045, 0.132, "Table 14"),
    "DSS-4": ("Madrid", 0.043, 0.132, "Table 15"),
}


def _complex_of(name: str) -> str:
    """DSS-14 -> Goldstone (1x/2x), DSS-34 -> Canberra (3x/4x), DSS-54 -> Madrid (5x/6x)."""
    first = int(name.split("-")[1][0])
    return {1: "DSS-1", 2: "DSS-1", 3: "DSS-2", 4: "DSS-2", 5: "DSS-4", 6: "DSS-4"}[first]


def rf_fields(name: str, accessed: str) -> dict[str, Any]:
    """The X-band figures for one antenna, with the sources they stand on."""
    out: dict[str, Any] = {"rx_x": None, "atmosphere_x": None, "sources": [], "field_sources": {}}
    if name in RX_70M:
        g, t = RX_70M[name]
        out["rx_x"] = {
            "frequency_mhz": 8420.0,
            "configuration": "X-only (S/X dichroic retracted), LNA-1/-2 HEMT",
            "gain_dbi": g,
            "gain_tol_adverse_db": 0.1,
            "gain_tol_favourable_db": 0.1,
            "t_amw_k": t,
            "t_amw_tol_adverse_k": 1.0,
            "t_amw_tol_favourable_k": 1.0,
            "module": "810-005 module 101 Rev. I, Table 2 (gain) and Table 4 (T_AMW)",
            "source_url": M101_URL,
        }
        out["sources"].append(
            {
                "url": M101_URL,
                "title": "DSN Telecommunications Link Design Handbook 810-005, module 101 "
                "Rev. I, 70-m Subnet Telecommunications Interfaces",
                "publisher": "NASA JPL Deep Space Network",
                "accessed": accessed,
            }
        )
        out["field_sources"]["rx_x"] = M101_URL
    elif name in RX_34M_TAMW:
        out["rx_x"] = {
            "frequency_mhz": 8425.0,
            "configuration": "X/Ka-mode, HEMT-1 (RCP)",
            "gain_dbi": 68.32,
            "gain_tol_adverse_db": 0.2,
            "gain_tol_favourable_db": 0.1,
            "t_amw_k": RX_34M_TAMW[name],
            "t_amw_tol_adverse_k": 2.0,
            "t_amw_tol_favourable_k": 1.0,
            "module": "810-005 module 104 Rev. O, Table 9",
            "source_url": M104_URL,
        }
        out["sources"].append(
            {
                "url": M104_URL,
                "title": "DSN Telecommunications Link Design Handbook 810-005, module 104 "
                "Rev. O, 34-m BWG Stations Telecommunications Interfaces",
                "publisher": "NASA JPL Deep Space Network",
                "accessed": accessed,
            }
        )
        out["field_sources"]["rx_x"] = M104_URL
    cx = _complex_of(name)
    cname, clear, adverse, table = ATM_X[cx]
    out["atmosphere_x"] = {
        "complex": cname,
        "zenith_clear_db": clear,
        "zenith_adverse_db": adverse,
        "cd_clear": 0.25,
        "cd_adverse": 0.99,
        "module": f"810-005 module 105 Rev. E, {table} (year average)",
        "source_url": M105_URL,
    }
    out["sources"].append(
        {
            "url": M105_URL,
            "title": "DSN Telecommunications Link Design Handbook 810-005, module 105 "
            "Rev. E, Atmospheric and Environmental Effects",
            "publisher": "NASA JPL Deep Space Network",
            "accessed": accessed,
        }
    )
    out["field_sources"]["atmosphere_x"] = M105_URL
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
        rf = rf_fields(name, accessed)
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
                "rx_x": rf["rx_x"],
                "atmosphere_x": rf["atmosphere_x"],
                "sources": [pdf_src, xlsx_src, *rf["sources"]],
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
                    **rf["field_sources"],
                },
                "assumed_fields": {},
                "unconfirmed_fields": ["bands", *(["rx_x"] if rf["rx_x"] is None else [])],
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
        "(810-005 module 301 Rev. O), with X-band receive gain and noise (modules 101, 104) and "
        "zenith attenuation (module 105) where published. Other networks' stations are not "
        "listed yet: their "
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
