"""The day's solar flux and geomagnetic activity, as NRLMSISE-00 takes them, from the
OMNI hourly files on disk (``data/spaceweather/omni_hourly``, NASA SPDF).

NRLMSISE-00 (Picone et al. 2002) is driven by the 10.7 cm solar flux of the day before,
its 81-day mean centred on the day, and seven ap numbers: the day's Ap, the 3-hour ap at
the time and 3, 6 and 9 hours before, and the means of the eight 3-hour values 12 to 33
and 36 to 57 hours before. NRLMSIS 2.x takes the same numbers (``pymsis``' storm-time
mode). OMNI carries the daily F10.7 and the 3-hour ap from NOAA NGDC, repeated on every
hour they cover.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import cdflib
import numpy as np
import numpy.typing as npt

from app.data.space_climate import omni_dir

FloatArray = npt.NDArray[np.float64]

#: OMNI marks a missing value with 999.9 (F10.7) or 999 (ap); a valid F10.7 is at most
#: 500 sfu and a valid ap at most 350 (the files' own VALIDMAX).
F107_MAX = 500.0
AP_MAX = 350.0
#: The 81-day mean of the flux reaches this many days to each side of the day.
HALF_MEAN_DAYS = 40

H3 = timedelta(hours=3)


@dataclass(frozen=True, slots=True)
class Indices:
    #: 10.7 cm flux of the day before, sfu.
    f107: float
    #: Its 81-day mean centred on the day (days with no value left out), sfu.
    f107a: float
    #: The seven ap numbers, in NRLMSISE-00's order.
    ap: tuple[float, ...]
    files: tuple[str, ...]


def _hours(
    start: datetime, end: datetime
) -> tuple[list[datetime], FloatArray, FloatArray, list[str]]:
    """The hours from ``start`` to ``end`` that the files cover, with the day's F10.7 and
    the 3-hour ap of each (NaN where OMNI has none), and the files read."""
    ts: list[datetime] = []
    f107: list[float] = []
    ap: list[float] = []
    used = []
    for p in sorted(omni_dir().glob("omni2_h0_mrg1hr_*_v01.cdf")):
        d = datetime.strptime(p.name[16:24], "%Y%m%d").replace(tzinfo=UTC)
        if d > end or d + timedelta(days=186) < start:
            continue
        c = cdflib.CDF(str(p))
        times = [
            datetime.fromisoformat(str(x)[:19]).replace(tzinfo=UTC)
            for x in cdflib.cdfepoch.to_datetime(c.varget("Epoch"))
        ]
        keep = [i for i, t in enumerate(times) if start <= t <= end]
        if not keep:
            continue
        used.append(p.name)
        ts += [times[i] for i in keep]
        f = np.asarray(c.varget("F10_INDEX"), dtype=np.float64)[keep]
        a = np.asarray(c.varget("AP_INDEX"), dtype=np.float64)[keep]
        f107 += list(np.where(f > F107_MAX, np.nan, f))
        ap += list(np.where(a > AP_MAX, np.nan, a))
    return ts, np.asarray(f107), np.asarray(ap), used


def compute(
    t: datetime,
    hours: list[datetime],
    f107_daily: FloatArray,
    ap_3h: FloatArray,
    files: tuple[str, ...] = (),
) -> Indices | None:
    """The indices for ``t`` (UTC) from hourly values: ``f107_daily[i]`` is the day's flux
    and ``ap_3h[i]`` the 3-hour ap in force at ``hours[i]`` (NaN: missing). None when a
    value NRLMSISE-00 needs is missing."""
    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
    at_hour = {x: i for i, x in enumerate(hours)}

    def ap_at(when: datetime) -> float:
        i = at_hour.get(when.replace(minute=0, second=0, microsecond=0))
        return float(ap_3h[i]) if i is not None else float("nan")

    def f107_on(d: datetime) -> float:
        i = at_hour.get(d + timedelta(hours=12))
        return float(f107_daily[i]) if i is not None else float("nan")

    values = (
        float(np.mean([ap_at(day + k * H3) for k in range(8)])),
        ap_at(t),
        ap_at(t - H3),
        ap_at(t - 2 * H3),
        ap_at(t - 3 * H3),
        float(np.mean([ap_at(t - timedelta(hours=12) - k * H3) for k in range(8)])),
        float(np.mean([ap_at(t - timedelta(hours=36) - k * H3) for k in range(8)])),
    )
    around = np.array(
        [f107_on(day + timedelta(days=k)) for k in range(-HALF_MEAN_DAYS, HALF_MEAN_DAYS + 1)]
    )
    prev = f107_on(day - timedelta(days=1))
    if np.isnan(prev) or np.any(np.isnan(values)) or np.all(np.isnan(around)):
        return None
    return Indices(prev, float(np.nanmean(around)), values, files)


def at_many(times: list[datetime]) -> list[Indices | None]:
    """``at`` for several times (UTC), reading the files once for all of them."""
    if not times:
        return []
    if any(t.tzinfo is None for t in times):
        raise ValueError("every time must carry its time zone (UTC)")
    utc = [t.astimezone(UTC) for t in times]
    first = min(utc).replace(hour=0, minute=0, second=0, microsecond=0)
    last = max(utc).replace(hour=0, minute=0, second=0, microsecond=0)
    ts, f107, ap, used = _hours(
        first - timedelta(days=HALF_MEAN_DAYS), last + timedelta(days=HALF_MEAN_DAYS + 1)
    )
    if not ts:
        return [None] * len(utc)
    return [compute(t, ts, f107, ap, tuple(used)) for t in utc]


def at(t: datetime) -> Indices | None:
    """The indices for ``t`` (UTC), or None when OMNI on disk lacks any of them."""
    return at_many([t])[0]
