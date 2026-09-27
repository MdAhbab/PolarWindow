"""The weather hindcast's results, as ``make hindcast-weather`` wrote them (T4, Verification).

``checked(region, rule_id)`` is true only when the hindcast for that rule and
region passed the plan's gate (``core.verification``); every share shown for
the rule then says "checked against observations".
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.config import get_settings


@lru_cache(maxsize=8)
def load(region: str) -> dict[str, Any] | None:
    p = get_settings().data_dir / "hindcast" / f"gefs_wind_{region}.json"
    if not p.exists():
        return None
    d: dict[str, Any] = json.loads(p.read_text())
    return d


def checked(region: str, rule_id: str) -> bool:
    d = load(region)
    return bool(d and d.get("rule_id") == rule_id and d.get("passes"))


def summary(region: str, rule_id: str) -> str | None:
    """One plain sentence on what the hindcast found for this rule, or None."""
    d = load(region)
    if not d or d.get("rule_id") != rule_id:
        return None
    leads = d.get("leads") or {}
    parts = []
    for lead in sorted(leads, key=int):
        x = leads[lead]
        skill = x.get("skill")
        ev = x["events"]
        seen = "no case" if ev == 0 else ("1 case" if ev == 1 else f"{ev} cases")
        parts.append(
            f"{lead} h: Brier skill {'not defined' if skill is None else f'{skill:.2f}'} over "
            f"{x['cases']} runs, with {seen} of the wind above the limit"
        )
    verdict = "passed" if d.get("passes") else "did not pass"
    return (
        f"Checked against {d['station']} ({d['event']}) for {d['period'].replace('..', ' to ')}: "
        + "; ".join(parts)
        + f". It {verdict} the gate ({d['gate']})."
    )
