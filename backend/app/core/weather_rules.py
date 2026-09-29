"""Launch weather rules against forecast numbers (T4, B1). Pure.

A model rule (a wind limit at a height) is checked member by member: the
share of an ensemble's runs that break it, ``k`` of ``N``, never pooled
across forecast systems. Winds at the rule's height come from the model's
10 m and 80 m winds on a logarithmic profile, ``u(z) = u10 + (u80 - u10)
ln(z / 10) / ln(8)``, which is exact for a neutral surface layer and is
labelled as interpolated wherever it is shown.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

#: Roughness length (m) of open, flat ground: with it a neutral logarithmic profile carries a 10 m
#: wind to a rule's height (and the rule's limit down to 10 m), as the weather check does.
OPEN_FLAT_Z0_M = 0.03

#: Metres per second in one of each unit a published limit uses.
SPEED_UNITS: dict[str, float] = {"m/s": 1.0, "mph": 0.44704, "kt": 1852.0 / 3600.0, "km/h": 1 / 3.6}


def to_m_s(value: float, unit: str) -> float:
    if unit not in SPEED_UNITS:
        raise ValueError(f"not a speed unit: {unit!r}")
    return value * SPEED_UNITS[unit]


def from_m_s(value: float, unit: str) -> float:
    return value / SPEED_UNITS[unit]


def speed_at(member: Mapping[str, float], height_m: float) -> float | None:
    """Wind speed at ``height_m`` from one run's 10 m and 80 m winds (log profile)."""
    try:
        u10, v10 = member["u10_m_s"], member["v10_m_s"]
        u80, v80 = member["u80_m_s"], member["v80_m_s"]
    except KeyError:
        return None
    f = math.log(max(height_m, 1.0) / 10.0) / math.log(8.0)
    u = u10 + (u80 - u10) * f
    v = v10 + (v80 - v10) * f
    return math.hypot(u, v)


def nearest_lead(
    leads: Mapping[str, Mapping[str, Any]], t: datetime, tolerance_s: float
) -> tuple[str, datetime] | None:
    """The forecast step whose valid time is nearest ``t``, if within ``tolerance_s``."""
    best: tuple[str, datetime] | None = None
    best_d = tolerance_s
    for key, lead in leads.items():
        valid = datetime.fromisoformat(str(lead["valid"]).replace("Z", "+00:00"))
        d = abs((valid - t).total_seconds())
        if d <= best_d:
            best, best_d = (key, valid), d
    return best


def breaks(value: float, limit: float, comparison: str) -> bool:
    """Whether ``value`` breaks a "do not launch if ... <comparison> limit" rule."""
    return {
        "gt": value > limit,
        "ge": value >= limit,
        "lt": value < limit,
        "le": value <= limit,
    }[comparison]


def count_breaking(
    members: Mapping[str, Mapping[str, float]], height_m: float, limit_m_s: float, comparison: str
) -> tuple[int, int]:
    """``(k, n)``: runs whose wind at the height breaks the limit, of the runs that have one."""
    speeds = [speed_at(m, height_m) for m in members.values()]
    got = [s for s in speeds if s is not None]
    return sum(breaks(s, limit_m_s, comparison) for s in got), len(got)


def lean(lo: float, hi: float) -> str | None:
    """The side of a limit an ensemble's share puts the wind on, or None when it does not.

    A single forecast says "over" or "under", which is a claim that the wind is more likely
    than not on that side. An ensemble's share, with its 95 % interval, contradicts that
    claim only when the whole interval is on the other side of one half.
    """
    if lo > 0.5:
        return "over"
    if hi < 0.5:
        return "under"
    return None


def _percent(x: float) -> str:
    pct = 100.0 * x
    return "0%" if pct == 0 else f"{pct:.1f}%" if pct < 10 else f"{pct:.0f}%"


def disagreements(
    one: Sequence[tuple[str, float, bool]],
    share: tuple[int, int, float, float] | None,
    unit: str,
    gap: float | None,
) -> list[str]:
    """Plain sentences for each pair of forecast systems that do not agree on a rule.

    ``one`` are the single forecasts as ``(system, wind at the rule's height in the limit's
    ``unit``, whether it breaks the limit)``; ``share`` is the ensemble's ``(k, n, lo, hi)``.
    A single forecast disagrees with the ensemble when its side is the one the ensemble's
    share interval excludes (:func:`lean`). Two single forecasts disagree when they fall on
    opposite sides of the limit and are further apart than ``gap`` (the typical error of
    one of them, so two values a hair either side of the limit are not called a
    disagreement); with no ``gap`` known, opposite sides are enough.
    """
    out: list[str] = []
    if share is not None:
        k, n, lo, hi = share
        side = lean(lo, hi)
        for name, value, over in one:
            if side is not None and (side == "over") != over:
                out.append(
                    f"{name} puts the wind at {value:.1f} {unit}, "
                    f"{'over' if over else 'under'} the limit, while {k} of {n} GEFS runs break it "
                    f"(95% range {_percent(lo)} to {_percent(hi)})."
                )
    for i, (a, va, oa) in enumerate(one):
        for b, vb, ob in one[i + 1 :]:
            if oa != ob and abs(va - vb) > (gap or 0.0):
                over_first = (a, va) if oa else (b, vb)
                under_first = (b, vb) if oa else (a, va)
                out.append(
                    f"{over_first[0]} puts the wind at {over_first[1]:.1f} {unit}, over the "
                    f"limit, and {under_first[0]} at {under_first[1]:.1f} {unit}, under it."
                )
    return out
