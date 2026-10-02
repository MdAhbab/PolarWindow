"""Read normalized, imported Copernicus waves; no network or NetCDF dependencies."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from app.config import get_settings

DATASET = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
SOURCE = "https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_WAV_001_027"


def utc(value: str) -> datetime:
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return date.replace(tzinfo=UTC) if date.tzinfo is None else date.astimezone(UTC)


@lru_cache(maxsize=4)
def _read(path: str, modified: int, size: int) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError("invalid normalized wave subset")
    return value


def wave_at(zone: tuple[float, float], when: datetime) -> dict[str, Any] | None:
    """Nearest grid cell/3-hour step; reject land, gaps, age and out-of-bounds queries."""
    path = get_settings().data_dir / "copernicus" / "waves.json"
    if not path.is_file():
        return None
    stat = path.stat()
    data = _read(str(path), stat.st_mtime_ns, stat.st_size)
    age = (datetime.now(UTC) - utc(data["imported_at"])).total_seconds()
    if not 0 <= age <= 24 * 3600:
        return None
    lat = np.asarray(data["latitude"])
    lon = (np.asarray(data["longitude"]) + 180) % 360 - 180
    if not min(lat) <= zone[0] <= max(lat) or not min(lon) <= zone[1] <= max(lon):
        return None
    index, gap = min(
        enumerate(abs((utc(t) - when).total_seconds()) for t in data["times"]),
        key=lambda pair: pair[1],
    )
    if gap > 1.5 * 3600:
        return None
    i, j = int(np.argmin(abs(lat - zone[0]))), int(np.argmin(abs(lon - zone[1])))
    value = data["VHM0"][index][i][j]
    if value is None:
        return None
    a, b = math.radians(zone[0]), math.radians(float(lat[i]))
    delta = math.radians(float(lon[j]) - zone[1])
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(delta / 2) ** 2
    distance = 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))
    if distance > 20:
        return None
    return {
        "wave_height_m": value,
        "valid": utc(data["times"][index]),
        "imported_at": utc(data["imported_at"]),
        "distance_km": distance,
        "source_url": data["source_url"],
        "source_sha256": data["source_sha256"],
        "note": data["note"],
    }
