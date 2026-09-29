"""One grid point's value from a few bytes of a simple-packed GRIB2 message on a Lambert grid.

HRRR's files in NOAA's archive on AWS (``noaa-hrrr-bdp-pds``) pack each field
with template 5.0 (simple packing): every value takes the same number of bits,
so the value at grid point ``k`` sits at a known bit of section 7 and a byte
range of a few bytes reads it. With the file's index giving where each message
starts, a point needs the message's first few hundred bytes (sections 0 to 6)
and one short range, instead of the 2.4 MB message.

The grid is template 3.30 (Lambert conformal, on a sphere, scanning west to
east and south to north, as HRRR's is). The grid point nearest a place is the
one the live product reads (``parsers.grib`` takes ecCodes' nearest point on a
Lambert grid). Anything else raises :class:`RangeError`. Layout: WMO Manual on
Codes (WMO-No. 306), GRIB2 templates 3.30, 5.0 and 7.0; projection: Snyder
(1987), *Map Projections: A Working Manual*, USGS PP 1395, eqs. 15-1 to 15-4.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

#: Bytes from a message's start that reach section 7 on HRRR's messages (about 190).
HEAD = 512
#: Radius of the sphere GRIB2 shape 6 names (m).
SHAPE6_RADIUS_M = 6_371_229.0


class RangeError(ValueError):
    """The message is not in the layout this module reads."""


def _sm(raw: bytes) -> int:
    """GRIB2 signed integer: the top bit is the sign, the rest the magnitude."""
    v = int.from_bytes(raw, "big")
    top = 1 << (8 * len(raw) - 1)
    return -(v & (top - 1)) if v & top else v


@dataclass(frozen=True, slots=True)
class Lambert:
    nx: int
    ny: int
    la1: float
    lo1: float
    lov: float
    latin1: float
    latin2: float
    dx: float
    dy: float
    radius: float

    def _cone(self) -> tuple[float, float]:
        p1, p2 = math.radians(self.latin1), math.radians(self.latin2)
        if abs(p1 - p2) < 1e-12:
            n = math.sin(p1)
        else:
            n = math.log(math.cos(p1) / math.cos(p2)) / math.log(
                math.tan(math.pi / 4 + p2 / 2) / math.tan(math.pi / 4 + p1 / 2)
            )
        f = math.cos(p1) * math.tan(math.pi / 4 + p1 / 2) ** n / n
        return n, f

    def _proj(self, lat: float, lon: float) -> tuple[float, float]:
        n, f = self._cone()
        rho = self.radius * f / math.tan(math.pi / 4 + math.radians(lat) / 2) ** n
        dl = (lon - self.lov + 180.0) % 360.0 - 180.0
        theta = n * math.radians(dl)
        return rho * math.sin(theta), -rho * math.cos(theta)

    def xy(self, lat: float, lon: float) -> tuple[float, float]:
        """Fractional grid column and row of ``lat, lon`` (row 0 is the southern edge)."""
        x0, y0 = self._proj(self.la1, self.lo1)
        x, y = self._proj(lat, lon)
        return (x - x0) / self.dx, (y - y0) / self.dy

    def nearest(self, lat: float, lon: float) -> int:
        """Index, in the message's order, of the grid point nearest ``lat, lon``."""
        x, y = self.xy(lat, lon)
        i, j = round(x), round(y)
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            raise RangeError(f"{lat}, {lon} is outside the grid")
        return j * self.nx + i


@dataclass(frozen=True, slots=True)
class Simple:
    """What sections 3 and 5 say, and where section 7's values start."""

    grid: Lambert
    n: int
    ref: float
    e: int
    d: int
    nbits: int
    data_at: int  # first byte of section 7's values, from the message's start
    total: int

    def span(self, k: int) -> tuple[int, int]:
        """First and last byte (from the message's start) holding value ``k``."""
        if not 0 <= k < self.n:
            raise RangeError(f"value {k} outside 0..{self.n - 1}")
        bit = k * self.nbits
        return self.data_at + bit // 8, self.data_at + (bit + self.nbits - 1) // 8

    def value(self, chunk: bytes, k: int) -> float:
        """Value ``k`` from the bytes :meth:`span` names."""
        a, b = self.span(k)
        if len(chunk) != b - a + 1:
            raise RangeError(f"{len(chunk)} bytes for a span of {b - a + 1}")
        word = int.from_bytes(chunk, "big")
        shift = (b - a + 1) * 8 - (k * self.nbits) % 8 - self.nbits
        x = (word >> shift) & ((1 << self.nbits) - 1) if self.nbits else 0
        return (self.ref + x * 2.0**self.e) * 10.0 ** (-self.d)


def layout(head: bytes) -> Simple:
    """Read sections 0 to 6 from a message's first bytes (:data:`HEAD` is enough for HRRR)."""
    if head[:4] != b"GRIB" or head[7] != 2:
        raise RangeError("not a GRIB2 message")
    total = struct.unpack(">Q", head[8:16])[0]
    at = 16
    grid: Lambert | None = None
    s5: bytes | None = None
    while True:
        if at + 5 > len(head):
            raise RangeError("the head ends before section 7")
        ln = struct.unpack(">I", head[at : at + 4])[0]
        sec = head[at + 4]
        if sec == 7:
            break
        s = head[at : at + ln]
        if len(s) < ln:
            raise RangeError("the head ends inside a section")
        if sec == 3:
            if struct.unpack(">H", s[12:14])[0] != 30:
                raise RangeError("not a Lambert conformal grid (3.30)")
            shape = s[14]
            if shape == 6:
                radius = SHAPE6_RADIUS_M
            elif shape == 1:
                radius = struct.unpack(">I", s[16:20])[0] / 10.0 ** s[15]
            else:
                raise RangeError(f"earth shape {shape} is not a sphere read here")
            if s[64] != 64:
                raise RangeError(f"scanning mode {s[64]} is not read here")
            grid = Lambert(
                nx=struct.unpack(">I", s[30:34])[0],
                ny=struct.unpack(">I", s[34:38])[0],
                la1=_sm(s[38:42]) * 1e-6,
                lo1=_sm(s[42:46]) * 1e-6,
                lov=_sm(s[51:55]) * 1e-6,
                dx=struct.unpack(">I", s[55:59])[0] * 1e-3,
                dy=struct.unpack(">I", s[59:63])[0] * 1e-3,
                latin1=_sm(s[65:69]) * 1e-6,
                latin2=_sm(s[69:73]) * 1e-6,
                radius=radius,
            )
        elif sec == 5:
            if struct.unpack(">H", s[9:11])[0] != 0:
                raise RangeError("not simple packing (5.0)")
            s5 = s
        elif sec == 6 and s[5] != 255:
            raise RangeError("a bit map is not read here")
        at += ln
    if grid is None or s5 is None:
        raise RangeError("no grid or packing section")
    return Simple(
        grid=grid,
        n=struct.unpack(">I", s5[5:9])[0],
        ref=struct.unpack(">f", s5[11:15])[0],
        e=_sm(s5[15:17]),
        d=_sm(s5[17:19]),
        nbits=s5[19],
        data_at=at + 5,
        total=total,
    )
