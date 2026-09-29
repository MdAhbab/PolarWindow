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
    system = f" using {d['system']}" if d.get("system") else ""
    span = f", {d['days_fetched']} forecast days" if d.get("days_fetched") else ""
    return (
        f"Checked against {d['station']} ({d['event']}){system} for "
        f"{d['period'].replace('..', ' to ')}{span}: "
        + "; ".join(parts)
        + f". It {verdict} the gate ({d['gate']})."
        + (f" It covers launches up to {max_lead_h(d)} h ahead." if d.get("passes") else "")
    )
