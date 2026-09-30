"""Measured air between 30 and 70 km near OSIRIS-REx's entry track, reduced to the two small
files that ``capsule_air`` compares the atmosphere models with (plan track H).

Run: ``uv run python -m app.validation.capsule_air_data`` (needs the network). The lidar's files
are HDF4, which ``pyhdf`` reads and the project does not depend on: run it with ``pyhdf`` on the
path, for example ``PYTHONPATH=<a folder holding only pyhdf> uv run python -m ...``. The originals
are kept under ``data/bulk/capsule_air`` (not committed); the two results are committed.

* ``data/capsule/saber_20230924.json``: NASA's TIMED/SABER limb sounder, Level 2A version 2.08
  (kinetic temperature, pressure and number density against tangent-point height), the day's
  orbits from NASA's CDAWeb copy of GATS's archive (``SABER_URL``). The profiles whose tangent
  point at 50 km lies between 28 and 49 N (the entry track runs from 37.3 N to 40.4 N, so this
  is about 10 degrees each way) are kept, with time, place and local solar time. The producer
  marks the files "Unvalidated".
* ``data/capsule/tmf_lidar_202309.json``: the temperature and number density profiles of the
  Rayleigh lidar of NASA JPL's Table Mountain Facility (34.4 N, 117.7 W; NDACC), every night from
  19 to 30 September 2023 that has a file (nine; none for 23 to 25 September; ``TMF_URL``). The
  temperature is worked out from the lidar's own relative density from the top down (Hauchecorne
  and Chanin 1980), started between 87 and 92.5 km (it varies by night) from an ancillary profile
  (the file names MERRA-2 as its source and says MSIS by default), so a start error of 20 K is
  0.5 K by 70 km and 0.2 K by 65 km (the density ratio, NRLMSIS 2.1). The density is the lidar's
  relative density scaled to an ancillary profile (the file names MERRA-2 again; the height of the
  scaling is the fill value, -999, so it is not given): its level, not its change with height,
  depends on that profile. The file's combined temperature uncertainty is 0.2 to 1.8 K from
  30 to 70 km. Its variable named as an ozone mixing ratio, ``NUMBER.DENSITY_BACKSCATTER``, is the
  air's number density in molecules per m^3 (a description copied wrongly in the file: the
  values are 3.7e23 at 30 km and 1.7e21 at 70 km).

Both are reduced to 1 km bins from 30 to 70 km (the instruments' vertical resolution is coarser):
the mean temperature, and the density as the geometric mean.
"""

from __future__ import annotations

import gzip
import importlib
import json
import math
import re
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.io import netcdf_file

from app.config import get_settings

FloatArray = npt.NDArray[np.float64]

SABER_URL = "https://cdaweb.gsfc.nasa.gov/sp_phys/data/timed/saber/level2a_netCDF/2023/267/"
TMF_URL = "https://www-air.larc.nasa.gov/pub/NDACC/PUBLIC/stations/table.mountain.ca/hdf/lidar/"
SABER_OUT = "capsule/saber_20230924.json"
LIDAR_OUT = "capsule/tmf_lidar_202309.json"
#: Tangent-point latitudes kept, degrees north, and the heights binned, km.
SABER_LAT = (28.0, 49.0)
BIN_LO_KM, BIN_HI_KM = 30, 70
LIDAR_FIRST, LIDAR_LAST = "20230919", "20230930"
LIDAR_FILE = re.compile(
    r"groundbased_lidar\.temperature_nasa\.jpl001_glass\.1\.1_table\.mountain\.ca_"
    r"(\d{8})t\d{6}z_\d{8}t\d{6}z_001\.hdf"
)


def _get(url: str, dest: Path) -> Path:
    """Download ``url`` to ``dest`` unless it is there (one retry)."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in (0, 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 (fixed https URLs)
                dest.write_bytes(r.read())
            return dest
        except OSError:
            if attempt:
                raise
    raise AssertionError("unreachable")


def _links(url: str, pattern: str) -> list[str]:
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310
        page = r.read().decode()
    return sorted({m.group(0) for m in re.finditer(pattern, page)})


def bin_km(z_km: FloatArray, x: FloatArray, *, geometric: bool = False) -> list[float | None]:
    """The mean of ``x`` in each 1 km bin from ``BIN_LO_KM`` to ``BIN_HI_KM`` (None: no valid
    point in the bin), four significant figures; ``geometric`` takes the geometric mean, for a
    density. A value that is not above zero, or not finite, is a missing one."""
    ok = np.isfinite(z_km) & np.isfinite(x) & (x > 0)
    z, y = z_km[ok], x[ok]
    out: list[float | None] = []
    for k in range(BIN_LO_KM, BIN_HI_KM):
        s = (z >= k) & (z < k + 1)
        if not s.any():
            out.append(None)
        elif geometric:
            out.append(float(f"{math.exp(float(np.mean(np.log(y[s])))):.4g}"))
        else:
            out.append(float(f"{float(np.mean(y[s])):.4g}"))
    return out


def saber(cache: Path) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    for name in _links(SABER_URL, r"SABER_L2A_2023267_\d+_02\.08\.nc\.gz"):
        raw = cache / name[:-3]
        if not raw.exists():
            raw.write_bytes(gzip.decompress(_get(SABER_URL + name, cache / name).read_bytes()))
        f = netcdf_file(str(raw), mmap=False)

        def v(k: str, f: Any = f) -> FloatArray:
            return np.array(f.variables[k][:], dtype=np.float64)

        z, temp, n = v("tpaltitude"), v("ktemp"), v("density")
        lat, lon, ms, lt, date = (
            v("tplatitude"),
            v("tplongitude"),
            v("time"),
            v("tpSolarLT"),
            v("date"),
        )
        for e in range(z.shape[0]):
            if int(date[e]) != 2023267:
                continue
            i = int(np.argmin(np.abs(z[e] - 50.0)))
            if not SABER_LAT[0] <= lat[e, i] <= SABER_LAT[1]:
                continue
            t_bin = bin_km(z[e], temp[e])  # SABER's -999 is not above zero
            if sum(x is not None for x in t_bin) < 20:
                continue
            when = datetime(2023, 9, 24, tzinfo=UTC) + timedelta(milliseconds=float(ms[e, i]))
            profiles.append(
                {
                    "time": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "lat_deg": round(float(lat[e, i]), 3),
                    "lon_deg": round(float(lon[e, i]), 3),
                    "local_solar_time_h": round(float(lt[e, i]) / 3.6e6, 2),
                    "temperature_k": t_bin,
                    "number_density_cm3": bin_km(z[e], n[e], geometric=True),
                    "file": name[:-3],
                }
            )
    profiles.sort(key=lambda p: p["time"])
    return {
        "instrument": "TIMED/SABER Level 2A version 2.08 (GATS; validation stamp: Unvalidated)",
        "source": SABER_URL,
        "z_km": [k + 0.5 for k in range(BIN_LO_KM, BIN_HI_KM)],
        "profiles": profiles,
    }


def lidar(cache: Path) -> dict[str, Any]:
    try:
        sd = importlib.import_module("pyhdf.SD")
    except ImportError as exc:
        raise SystemExit(
            "the lidar's files are HDF4: run with pyhdf on the path (not a project dependency)"
        ) from exc
    names = [
        n
        for n in _links(TMF_URL, LIDAR_FILE.pattern)
        if (m := LIDAR_FILE.fullmatch(n)) and LIDAR_FIRST <= m.group(1) <= LIDAR_LAST
    ]
    profiles: list[dict[str, Any]] = []
    for name in names:
        s = sd.SD(str(_get(TMF_URL + name, cache / name)), sd.SDC.READ)

        def g(k: str, s: Any = s) -> FloatArray:
            return np.asarray(s.select(k)[:], dtype=np.float64)

        z = g("ALTITUDE") / 1000.0
        temp = g("TEMPERATURE_BACKSCATTER")
        usable = temp > 0  # the file's fill value is -999
        mid = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(days=float(g("DATETIME")[0]))
        attrs = s.attributes()
        profiles.append(
            {
                "time": mid.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "start": attrs["DATA_START_DATE"],
                "stop": attrs["DATA_STOP_DATE"],
                "lat_deg": round(float(g("LATITUDE.INSTRUMENT")[0]), 2),
                "lon_deg": round(float(g("LONGITUDE.INSTRUMENT")[0]), 2),
                "temperature_k": bin_km(z, temp),
                "temperature_uncertainty_k": bin_km(
                    z,
                    np.where(
                        usable, g("TEMPERATURE_BACKSCATTER_UNCERTAINTY.COMBINED.STANDARD"), np.nan
                    ),
                ),
                # molecules per m^3 in the file, per cm^3 here (as SABER's)
                "number_density_cm3": bin_km(
                    z,
                    np.where(usable, g("NUMBER.DENSITY_BACKSCATTER") * 1e-6, np.nan),
                    geometric=True,
                ),
                "file": name,
            }
        )
    profiles.sort(key=lambda p: p["time"])
    return {
        "instrument": "NASA JPL Table Mountain Facility Rayleigh lidar (NDACC), temperature",
        "source": TMF_URL,
        "z_km": [k + 0.5 for k in range(BIN_LO_KM, BIN_HI_KM)],
        "profiles": profiles,
    }


def main() -> None:
    data = get_settings().data_dir
    cache = data / "bulk" / "capsule_air"
    for rel, part in ((SABER_OUT, saber), (LIDAR_OUT, lidar)):
        out = part(cache)
        (data / rel).write_text(json.dumps(out, separators=(",", ":")) + "\n")
        print(f"{rel}: {len(out['profiles'])} profiles", file=sys.stderr)


if __name__ == "__main__":
    main()
