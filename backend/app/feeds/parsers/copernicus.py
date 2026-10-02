"""Decode a user-downloaded Copernicus regional wave NetCDF subset."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from app.data.copernicus_wave import DATASET, SOURCE, utc


def import_subset(path: Path) -> dict[str, Any]:
    from netCDF4 import Dataset, num2date

    with Dataset(path) as ds:
        product = getattr(ds, "subset:productId", "GLOBAL_ANALYSISFORECAST_WAV_001_027")
        dataset = getattr(ds, "subset:datasetId", DATASET)
        if product != "GLOBAL_ANALYSISFORECAST_WAV_001_027" or not str(dataset).startswith(DATASET):
            raise ValueError("expected the Global Ocean Waves 3-hourly dataset")
        for name in ("VHM0", "time", "latitude", "longitude"):
            if name not in ds.variables:
                raise ValueError(f"missing {name}")
        variable = ds.variables["VHM0"]
        if getattr(variable, "standard_name", "sea_surface_wave_significant_height") != (
            "sea_surface_wave_significant_height"
        ):
            raise ValueError("VHM0 must describe total sea surface wave significant height")
        if variable.units not in ("m", "metres", "meters"):
            raise ValueError("VHM0 must be significant wave height in metres")
        if variable.dimensions != ("time", "latitude", "longitude"):
            raise ValueError("expected time, latitude, longitude dimensions")
        calendar = getattr(ds.variables["time"], "calendar", "standard")
        if calendar not in ("standard", "gregorian", "proleptic_gregorian"):
            raise ValueError("expected Gregorian UTC times")
        times = num2date(
            ds.variables["time"][:],
            ds.variables["time"].units,
            calendar=calendar,
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=True,
        )
        if isinstance(times, datetime):
            raise ValueError("time must be an array")
        lat = np.asarray(ds.variables["latitude"][:], dtype=float)
        lon = np.asarray(ds.variables["longitude"][:], dtype=float)
        if (
            getattr(ds.variables["latitude"], "units", "") != "degrees_north"
            or getattr(ds.variables["longitude"], "units", "") != "degrees_east"
        ):
            raise ValueError("expected latitude/longitude coordinates in degrees")
        for name, coords in [("latitude", lat), ("longitude", lon)]:
            if coords.ndim != 1 or not np.isfinite(coords).all() or coords.size < 2:
                raise ValueError(f"invalid {name} axis")
            if not (np.all(np.diff(coords) > 0) or np.all(np.diff(coords) < 0)):
                raise ValueError(f"{name} axis must be strictly monotonic")
        if np.any(abs(lat) > 90) or np.any((lon < -180) | (lon > 360)):
            raise ValueError("invalid latitude/longitude range")
        dates = [t.replace(tzinfo=UTC).isoformat() for t in times]
        if len(dates) < 1 or any(utc(b) <= utc(a) for a, b in pairwise(dates)):
            raise ValueError("times must strictly increase")
        if variable.size > 2_000_000:
            raise ValueError("download a regional/time subset (at most two million cells)")
        # netCDF4 decodes packing and masks _FillValue/missing_value by default.
        heights = np.ma.asarray(variable[:], dtype=float).filled(np.nan)  # type: ignore[no-untyped-call]
        heights[(heights < 0) | (heights > 30)] = np.nan
        if not np.isfinite(heights).any():
            raise ValueError("subset has no valid ocean wave values")
        values = [
            [[float(v) if np.isfinite(v) else None for v in row] for row in frame]
            for frame in heights
        ]
        attrs = {key: str(ds.getncattr(key)) for key in ds.ncattrs()}
    return {
        "dataset": DATASET,
        "source_url": SOURCE,
        "imported_at": datetime.now(UTC).isoformat(),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "attributes": attrs,
        "times": dates,
        "latitude": lat.tolist(),
        "longitude": lon.tolist(),
        "VHM0": values,
        "note": "User-downloaded Copernicus subset; forecast issuance time not inferred "
        "from subset creation time. Wave height only; no wind observation or forecast.",
    }
