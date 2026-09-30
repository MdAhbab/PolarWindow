"""Point values from the first bytes of a GRIB2 message (complex packing with spatial differencing).

The GEFSv12 reforecast on AWS keeps each global 0.25 degree field as one GRIB2
message of about 800 kB, packed with template 5.3 (complex packing and second
order spatial differencing). Every value is rebuilt from the ones before it in
the grid's order, so a point cannot be read on its own; but a point in the
northern part of the grid needs only the message up to it. The Cape is about a
third of the way down the grid, so reading the prefix instead of the message
cuts what is fetched by more than half.

This module reads that layout without ecCodes (numpy only): sections 3 (regular
latitude-longitude, scanning west to east and north to south), 5 (template 5.3,
no missing values) and 7, and decodes the first ``k`` values. Anything else
raises :class:`PrefixError`, and the caller reads the whole message instead.
The layout is WMO Manual on Codes (WMO-No. 306), GRIB2 template 5.3 and 7.3;
the decoding follows NCEP's g2clib ``comunpack``.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.feeds.parsers.grib_ranges import sign_magnitude


class PrefixError(ValueError):
    """The message is not in the layout this module reads, or the prefix is too short."""


@dataclass(frozen=True, slots=True)
class Grid:
    ni: int
    nj: int
    la1: float
    lo1: float
    di: float
    dj: float

    def neighbours(self, lat: float, lon: float) -> tuple[list[int], list[float]]:
        """Indices (in the message's order) of the four points around ``lat, lon`` and
        their bilinear weights."""
        x = ((lon - self.lo1) % 360.0) / self.di
        y = (self.la1 - lat) / self.dj
        i0, j0 = math.floor(x), math.floor(y)
        tx, ty = x - i0, y - j0
        if not 0 <= j0 < self.nj - 1:
            raise PrefixError(f"latitude {lat} is outside the grid")
        i1 = (i0 + 1) % self.ni
        row0, row1 = j0 * self.ni, (j0 + 1) * self.ni
        idx = [row0 + i0, row0 + i1, row1 + i0, row1 + i1]
        w = [(1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty]
        return idx, w


@dataclass(frozen=True, slots=True)
class Layout:
    """What sections 0 to 6 say, and where section 7's parts start (bytes from the start)."""

    grid: Grid
    n: int
    ref: float
    e: int
    d: int
    nbits: int
    ng: int
    wref: int
    wbits: int
    lref: int
    linc: int
    last: int
    lbits: int
    order: int
    octs: int
    data_at: int  # first byte of section 7's data (after its 5-byte header)
    total: int  # the message's length

    @property
    def meta_end(self) -> int:
        """First byte after the groups' references, widths and lengths."""
        b = self.data_at + self.octs * (self.order + 1)
        for bits in (self.nbits, self.wbits, self.lbits):
            b += (self.ng * bits + 7) // 8
        return b


def layout(buf: bytes) -> Layout:
    """Read sections 0 to 6 from the start of a message (a few hundred bytes are enough)."""
    if buf[:4] != b"GRIB" or buf[7] != 2:
        raise PrefixError("not a GRIB2 message")
    total = struct.unpack(">Q", buf[8:16])[0]
    at = 16
    grid: Grid | None = None
    s5: bytes | None = None
    while True:
        if at + 5 > len(buf):
            raise PrefixError("prefix ends before section 7")
        ln = struct.unpack(">I", buf[at : at + 4])[0]
        sec = buf[at + 4]
        if sec == 7:
            break
        s = buf[at : at + ln]
        if len(s) < ln:
            raise PrefixError("prefix ends inside a header section")
        if sec == 3:
            if struct.unpack(">H", s[12:14])[0] != 0:
                raise PrefixError("not a regular latitude-longitude grid")
            if s[71] != 0:
                raise PrefixError(f"scanning mode {s[71]} is not read here")
            grid = Grid(
                ni=struct.unpack(">I", s[30:34])[0],
                nj=struct.unpack(">I", s[34:38])[0],
                la1=sign_magnitude(s[46:50]) * 1e-6,
                lo1=sign_magnitude(s[50:54]) * 1e-6,
                di=struct.unpack(">I", s[63:67])[0] * 1e-6,
                dj=struct.unpack(">I", s[67:71])[0] * 1e-6,
            )
        elif sec == 5:
            if struct.unpack(">H", s[9:11])[0] != 3:
                raise PrefixError("not complex packing with spatial differencing (5.3)")
            if s[22] != 0:
                raise PrefixError("missing values are not read here")
            s5 = s
        elif sec == 6 and s[5] != 255:
            raise PrefixError("a bit map is not read here")
        at += ln
    if grid is None or s5 is None:
        raise PrefixError("no grid or packing section")
    return Layout(
        grid=grid,
        n=struct.unpack(">I", s5[5:9])[0],
        ref=struct.unpack(">f", s5[11:15])[0],
        e=sign_magnitude(s5[15:17]),
        d=sign_magnitude(s5[17:19]),
        nbits=s5[19],
        ng=struct.unpack(">I", s5[31:35])[0],
        wref=s5[35],
        wbits=s5[36],
        lref=struct.unpack(">I", s5[37:41])[0],
        linc=s5[41],
        last=struct.unpack(">I", s5[42:46])[0],
        lbits=s5[46],
        order=s5[47],
        octs=s5[48],
        data_at=at + 5,
        total=total,
    )


def _fixed(buf: npt.NDArray[np.uint8], bit0: int, count: int, bits: int) -> npt.NDArray[np.int64]:
    """``count`` unsigned integers of ``bits`` bits each, starting at bit ``bit0``."""
    if bits == 0:
        return np.zeros(count, dtype=np.int64)
    raw = np.unpackbits(buf, count=bit0 + count * bits)[bit0:].reshape(count, bits)
    out: npt.NDArray[np.int64] = (
        raw.astype(np.int64) << np.arange(bits - 1, -1, -1, dtype=np.int64)
    ).sum(axis=1)
    return out


def _variable(
    buf: npt.NDArray[np.uint8], offsets: npt.NDArray[np.int64], widths: npt.NDArray[np.int64]
) -> npt.NDArray[np.int64]:
    """One unsigned integer at each bit offset, each ``width`` bits (at most 57) long."""
    padded = np.concatenate([buf, np.zeros(8, dtype=np.uint8)])
    byte = offsets >> 3
    word = np.zeros(len(offsets), dtype=np.uint64)
    for k in range(8):
        word |= padded[byte + k].astype(np.uint64) << np.uint64(56 - 8 * k)
    shift = (np.uint64(64) - (offsets & 7).astype(np.uint64) - widths.astype(np.uint64)).astype(
        np.uint64
    )
    mask = (np.uint64(1) << widths.astype(np.uint64)) - np.uint64(1)
    return ((word >> shift) & mask).astype(np.int64)


def _groups(lay: Layout, buf: npt.NDArray[np.uint8]) -> tuple[npt.NDArray[np.int64], ...]:
    """The groups' references, widths and lengths, and the bit where the packed values start."""
    bit = (lay.data_at + lay.octs * (lay.order + 1)) * 8
    gref = _fixed(buf, bit, lay.ng, lay.nbits)
    bit += ((lay.ng * lay.nbits + 7) // 8) * 8
    gw = _fixed(buf, bit, lay.ng, lay.wbits) + lay.wref
    bit += ((lay.ng * lay.wbits + 7) // 8) * 8
    gl = _fixed(buf, bit, lay.ng, lay.lbits) * lay.linc + lay.lref
    gl[-1] = lay.last
    return gref, gw, gl


def bytes_needed(lay: Layout, head: bytes, k: int) -> int:
    """How many bytes from the message's start decode the first ``k`` values
    (``head`` must reach :attr:`Layout.meta_end`)."""
    if len(head) < lay.meta_end:
        raise PrefixError("prefix ends before the groups' descriptions")
    buf = np.frombuffer(head, dtype=np.uint8)
    _, gw, gl = _groups(lay, buf)
    g = int(np.searchsorted(np.cumsum(gl), k))  # the group holding value k - 1
    bits = int(np.sum(gw[: g + 1] * gl[: g + 1]))
    return min(lay.total, lay.meta_end + (bits + 7) // 8 + 8)


def decode_prefix(head: bytes, k: int) -> npt.NDArray[np.float64]:
    """The first ``k`` values of the field, from the message's first bytes."""
    lay = layout(head)
    if not 2 <= k <= lay.n:
        raise PrefixError(f"k={k} outside 2..{lay.n}")
    need = bytes_needed(lay, head, k)
    if len(head) < min(need, lay.total) - 8:
        raise PrefixError(f"prefix of {len(head)} bytes, {need} needed")
    buf = np.frombuffer(head, dtype=np.uint8)
    gref, gw, gl = _groups(lay, buf)
    g = int(np.searchsorted(np.cumsum(gl), k))
    lens = gl[: g + 1]
    widths = np.repeat(gw[: g + 1], lens)[:k]
    refs = np.repeat(gref[: g + 1], lens)[:k]
    start = lay.meta_end * 8
    offs = start + np.concatenate([[0], np.cumsum(widths[:-1])]).astype(np.int64)
    f = _variable(buf, offs, widths) + refs
    # Spatial differencing: the first ``order`` values are given, the rest are differences.
    at = lay.data_at
    o = lay.octs
    ival1 = sign_magnitude(head[at : at + o])
    ival2 = sign_magnitude(head[at + o : at + 2 * o]) if lay.order == 2 else 0
    minsd = sign_magnitude(head[at + lay.order * o : at + (lay.order + 1) * o])
    if lay.order == 1:
        f[0] = ival1
        f[1:] += minsd
        f = np.cumsum(f)
    elif lay.order == 2:
        d2 = f[2:] + minsd
        first = np.concatenate([[ival2 - ival1], (ival2 - ival1) + np.cumsum(d2)])
        f = np.concatenate([[ival1], ival1 + np.cumsum(first)])
    else:
        raise PrefixError(f"spatial differencing of order {lay.order}")
    scale = 2.0**lay.e * 10.0 ** (-lay.d)
    vals: npt.NDArray[np.float64] = (lay.ref * 10.0 ** (-lay.d)) + f.astype(np.float64) * scale
    return vals


def points(head: bytes, where: list[tuple[float, float]]) -> list[float]:
    """Bilinear value at each (lat, lon), from a prefix reaching the southernmost point."""
    lay = layout(head)
    nb = [lay.grid.neighbours(lat, lon) for lat, lon in where]
    k = max(max(idx) for idx, _ in nb) + 1
    vals = decode_prefix(head, k)
    return [float(sum(vals[i] * w for i, w in zip(idx, ws, strict=True))) for idx, ws in nb]


def prefix_points(k_of: list[tuple[float, float]], lay: Layout) -> int:
    """How many values (from the start) cover the four neighbours of every point."""
    return max(max(lay.grid.neighbours(lat, lon)[0]) for lat, lon in k_of) + 1
