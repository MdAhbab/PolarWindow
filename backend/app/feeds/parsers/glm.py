"""GOES Geostationary Lightning Mapper (GLM) Level 2 flash files: flashes near the pads.

Each file (NetCDF-4, 20 seconds of data) lists flashes with their centroid
latitude and longitude, the time of their first event and a quality flag.
Only flashes flagged good (0) are counted. A body holds several files, each
framed by its length (8 bytes, big-endian), in the order they were fetched.

This module is the only one that reads HDF5 (h5py).
"""

from __future__ import annotations

import io
import math
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import h5py
import numpy as np
import numpy.typing as npt

from app.feeds.base import ParseError

FloatArray = npt.NDArray[np.float64]

R_EARTH_KM = 6371.0
NMI_KM = 1.852
EPOCH_2000 = datetime(2000, 1, 1, 12, tzinfo=UTC)


def frame(files: list[bytes]) -> bytes:
    """Files as one body: each prefixed with its length."""
    return b"".join(struct.pack(">Q", len(f)) + f for f in files)


def unframe(body: bytes) -> list[bytes]:
    out, i = [], 0
    while i < len(body):
        if i + 8 > len(body):
            raise ParseError("a GLM body ends inside a length prefix")
        (n,) = struct.unpack(">Q", body[i : i + 8])
        if i + 8 + n > len(body):
            raise ParseError("a GLM file in the body is truncated")
        out.append(body[i + 8 : i + 8 + n])
        i += 8 + n
    return out


@dataclass(frozen=True, slots=True)
class Flashes:
    start: datetime  # time coverage of the file
    end: datetime
    platform: str
    lat: FloatArray
    lon: FloatArray
    t: list[datetime]  # first event of each flash


def _unpacked(ds: h5py.Dataset) -> FloatArray:
    raw = ds[()]
    if ds.attrs.get("_Unsigned", b"false") in (b"true", "true"):
        raw = raw.astype(np.int64) % (1 << (8 * ds.dtype.itemsize))
    v = np.asarray(raw, dtype=np.float64)
    if "scale_factor" in ds.attrs:
        v = v * float(np.asarray(ds.attrs["scale_factor"]).ravel()[0])
    if "add_offset" in ds.attrs:
        v = v + float(np.asarray(ds.attrs["add_offset"]).ravel()[0])
    return v


def _attr_time(f: h5py.File, name: str) -> datetime:
    v = f.attrs.get(name)
    if v is None:
        raise ParseError(f"GLM file without {name}")
    text = v.decode() if isinstance(v, bytes | np.bytes_) else str(v)
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def read(data: bytes) -> Flashes:
    """The good-quality flashes of one GLM L2 LCFA file."""
    try:
        f = h5py.File(io.BytesIO(data), "r")
    except OSError as exc:
        raise ParseError(f"not a GLM NetCDF-4 file: {exc}") from exc
    with f:
        for k in ("flash_lat", "flash_lon", "flash_time_offset_of_first_event", "product_time"):
            if k not in f:
                raise ParseError(f"GLM file without {k}")
        lat = np.asarray(f["flash_lat"][()], dtype=np.float64)
        lon = np.asarray(f["flash_lon"][()], dtype=np.float64)
        dt = _unpacked(f["flash_time_offset_of_first_event"])
        base = EPOCH_2000 + timedelta(seconds=float(f["product_time"][()]))
        good = np.ones(lat.shape, dtype=bool)
        if "flash_quality_flag" in f:
            good = _unpacked(f["flash_quality_flag"]) == 0
        good &= np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
        platform = f.attrs.get("platform_ID", b"GOES")
        return Flashes(
            start=_attr_time(f, "time_coverage_start"),
            end=_attr_time(f, "time_coverage_end"),
            platform=platform.decode()
            if isinstance(platform, bytes | np.bytes_)
            else str(platform),
            lat=lat[good],
            lon=lon[good],
            t=[base + timedelta(seconds=float(x)) for x in dt[good]],
        )


def distance_km(lat0: float, lon0: float, lat: FloatArray, lon: FloatArray) -> FloatArray:
    p0, p = math.radians(lat0), np.radians(lat)
    c = math.sin(p0) * np.sin(p) + math.cos(p0) * np.cos(p) * np.cos(np.radians(lon - lon0))
    return np.asarray(R_EARTH_KM * np.arccos(np.clip(c, -1.0, 1.0)), dtype=np.float64)
