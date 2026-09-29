"""The weather hindcast's results (T4, Verification).

``checked(region, rule_id)`` is true only when the check for that rule and region
passed the plan's gate (``core.verification``); every share shown for the rule
then says "checked against observations". Two checks may be on disk: the
multi-year one (``make hindcast-reforecast``, GEFS v12 reforecast, 13 years) and
the single-year one (``make hindcast-weather``, the archived live ensemble, 2025).
The multi-year one is used when it exists, since it has the cases the rare event
needs; the other stands in when it does not.

A check covers the leads it scored (24 and 48 h). A share for a launch further
out is not covered by it: ``checked`` with ``lead_h`` says false there.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.config import get_settings

#: Files in ``data/hindcast/``, the one to trust first first.
FILES = ("gefs_reforecast_wind_{region}.json", "gefs_wind_{region}.json")


@lru_cache(maxsize=8)
def load(region: str) -> dict[str, Any] | None:
    folder = get_settings().data_dir / "hindcast"
    for name in FILES:
        p = folder / name.format(region=region)
        if p.exists():
            d: dict[str, Any] = json.loads(p.read_text())
            if d.get("leads"):
                return d
    return None


def max_lead_h(d: dict[str, Any]) -> int:
    """The furthest lead the check scored, in hours."""
    return max((int(k) for k in d.get("leads") or {}), default=0)


def reach_h(region: str) -> int:
    """How far ahead the check for this region reaches, in hours (0 with no check)."""
    d = load(region)
    return max_lead_h(d) if d else 0


def checked(region: str, rule_id: str, lead_h: float | None = None) -> bool:
    """Whether shares for this rule are checked against observations, at ``lead_h`` if given."""
    d = load(region)
    if not (d and d.get("rule_id") == rule_id and d.get("passes")):
        return False
    return lead_h is None or lead_h <= max_lead_h(d)


def _lead_words(lead: str, x: dict[str, Any]) -> str:
    ev = x["events"]
    seen = "no case" if ev == 0 else ("1 case" if ev == 1 else f"{ev} cases")
    skill = x.get("skill")
    if skill is None:
        brier = "Brier skill not worked out" + (
            " (too few cases above the limit)" if x.get("skill_note") else ""
        )
    else:
        span = x.get("skill_95")
        brier = f"Brier skill {skill:.2f}" + (
            f" (95 % {span[0]:.2f} to {span[1]:.2f})" if span else ""
        )
    crps = x.get("crps_skill")
    tail = ""
    if crps is not None:
        span = x.get("crps_skill_95")
        tail = f"; CRPS skill {crps:.2f}" + (f" ({span[0]:.2f} to {span[1]:.2f})" if span else "")
    return f"{lead} h: {brier} over {x['cases']} cases, {seen} of the wind above the limit{tail}"


def summary(region: str, rule_id: str) -> str | None:
    """One plain sentence on what the check found for this rule, or None."""
    d = load(region)
    if not d or d.get("rule_id") != rule_id:
        return None
    leads = d.get("leads") or {}
    parts = [_lead_words(lead, leads[lead]) for lead in sorted(leads, key=int)]
    verdict = "passed" if d.get("passes") else "did not pass"
    system = f"; forecasts from {d['system']}" if d.get("system") else ""
    span = f", {d['days_fetched']} forecast days" if d.get("days_fetched") else ""
    return (
        f"Checked against {d['station']} ({d['event']}{system}) for "
        f"{d['period'].replace('..', ' to ')}{span}: "
        + "; ".join(parts)
        + f". It {verdict} the gate ({d['gate']})."
        + (f" It covers launches up to {max_lead_h(d)} h ahead." if d.get("passes") else "")
    )


# ---------------------------------------------------------------------------
# HRRR's one forecast against the station (make hindcast-hrrr)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=8)
def hrrr_load(region: str) -> dict[str, Any] | None:
    p = get_settings().data_dir / "hindcast" / f"hrrr_wind_{region}.json"
    if not p.exists():
        return None
    d: dict[str, Any] = json.loads(p.read_text())
    return d if d.get("leads") else None


def _hrrr_lead(d: dict[str, Any], lead_h: float) -> dict[str, Any] | None:
    """The scored lead nearest ``lead_h`` (the feed keeps 1, 6, 12 and 18 h)."""
    leads = d.get("leads") or {}
    if not leads:
        return None
    key = min(leads, key=lambda k: abs(int(k) - lead_h))
    x: dict[str, Any] = leads[key]
    return x if x.get("cases") else None


def _range_pct(span: list[float] | tuple[float, float] | None, closer: bool) -> str:
    """`` (95 % 22 to 31%)``: a skill's interval, said in the direction the words give the skill."""
    if not span:
        return ""
    lo, hi = (span[0], span[1]) if closer else (-span[1], -span[0])
    return f" (95 % {100 * lo:.0f} to {100 * hi:.0f}%)"


def hrrr_error_m_s(region: str, lead_h: float) -> float | None:
    """Root-mean-square error of HRRR's 10 m wind at the lead, m/s, or None if not checked."""
    d = hrrr_load(region)
    x = _hrrr_lead(d, lead_h) if d else None
    return None if x is None else x.get("rmse_m_s")


def hrrr_words(region: str, lead_h: float) -> str | None:
    """How HRRR's 10 m wind did against the station's, in plain words, or None."""
    d = hrrr_load(region)
    x = _hrrr_lead(d, lead_h) if d else None
    if d is None or x is None:
        return None
    years = d.get("years") or []
    span = f"{years[0]} to {years[-1]}" if years else "the years checked"
    bias = x["bias_m_s"]
    skill = x.get("mae_skill")
    lean = (
        "no higher or lower than the station's"
        if round(abs(bias), 1) == 0.0
        else f"{abs(bias):.1f} m/s {'above' if bias > 0 else 'below'} the station's"
    )
    text = (
        f"Checked against {d['station']} for {span} ({x['cases']} runs at this lead): HRRR's 10 m "
        f"wind was off by {x['mae_m_s']:.1f} m/s on average, {lean}"
    )
    if skill is not None:
        text += (
            f", and {abs(100 * skill):.0f}% {'closer to' if skill >= 0 else 'further from'} what "
            "was measured than the station's usual wind for that month and hour"
            + _range_pct(x.get("mae_skill_95"), skill >= 0)
        )
    text += ". "
    c = d.get("call_all_leads") or {}
    if c.get("cases"):
        if c["events"] == 0:
            text += (
                f"The station never reported wind above the limit at 10 m in those runs, so its "
                f"over-or-under call is not tested ({c['called_over']} calls of over)."
            )
        else:
            text += (
                f"At the limit brought to 10 m, over all leads: the station reported wind above it "
                f"{c['events']} times in {c['cases']} runs, HRRR called {c['hits']} of them, and "
                f"{c['false_alarms']} of its {c['called_over']} calls of over were wrong."
            )
    return text.strip()
