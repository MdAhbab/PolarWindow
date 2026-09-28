"""What an agent reads of a mission section: at most 200 numbers (ADR-6, amended).

A section's answer is written for a screen: plot series, every source's URL and
snapshot id, the uncertainty block of ``meta``, lists of dozens of windows. Handed
to a model whole, those widen the grounding pool until almost any number is
"grounded" (D23), and bury the few numbers a question is about. This keeps each
value with its ± (or the reason it has none), drops what only a chart needs, and
cuts long lists, saying what was left out so the agent can say so too. Pure: no
I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.guards import flatten_numbers

#: Most numbers one tool result may carry.
MAX_NUMBERS = 200
#: Most items of any list shown before the numbers are counted.
MAX_ITEMS = 12
#: Keys only a chart or a download needs; dropped wherever they appear.
PLOT_KEYS = frozenset({"samples", "track", "series", "points"})
#: Keys that carry no fact an answer could use.
NOISE_KEYS = frozenset({"snapshot_id", "licence", "compute_ms", "engines", "uncertainty", "url"})
_QUANTITY_CORE = ("value", "unit", "provenance")
_QUANTITY_EXTRA = ("pm", "lo", "hi", "factor")
_QUANTITY_WORDS = ("missing_reason", "no_margin_reason")


def _is_quantity(d: dict[str, Any]) -> bool:
    return "value" in d and "provenance" in d and "unit" in d


def _quantity(d: dict[str, Any]) -> dict[str, Any]:
    out = {k: d[k] for k in _QUANTITY_CORE}
    extra = {k: d[k] for k in _QUANTITY_EXTRA if d.get(k) is not None}
    if d["unit"] == "s since epoch" and isinstance(d["value"], int | float):
        # A time: written as one, so an answer can quote the date rather than work it out.
        at = datetime.fromtimestamp(float(d["value"]), UTC)
        out["value"] = at.isoformat(timespec="seconds").replace("+00:00", "Z")
        out["unit"] = "UTC"
        extra = {f"{k}_s": v for k, v in extra.items()}
    out.update(extra)
    if d.get("open"):
        out["open"] = True
    out.update({k: d[k] for k in _QUANTITY_WORDS if d.get(k)})
    return out


def _meta(m: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: m[k] for k in ("computed_at", "stale") if k in m}
    names = [s.get("name") for s in m.get("sources") or [] if isinstance(s, dict)]
    if names:
        out["sources"] = [n for n in names if n]
    return out


def _shrink(obj: Any, path: str, left_out: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        if _is_quantity(obj):
            return _quantity(obj)
        out = {}
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k in PLOT_KEYS and isinstance(v, list):
                if v:
                    left_out[p] = f"{len(v)} points of a plot series"
                continue
            if k in NOISE_KEYS:
                continue
            if k == "meta" and isinstance(v, dict):
                out[k] = _meta(v)
                continue
            out[k] = _shrink(v, p, left_out)
        return out
    if isinstance(obj, list):
        items = obj
        if len(obj) > MAX_ITEMS:
            left_out[path] = f"first {MAX_ITEMS} of {len(obj)}"
            items = obj[:MAX_ITEMS]
        return [_shrink(v, f"{path}[]", left_out) for v in items]
    return obj


def _lists(obj: Any, path: str = "") -> list[tuple[str, list[Any], int]]:
    """Every list in ``obj`` with its path and how many numbers it holds."""
    out: list[tuple[str, list[Any], int]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_lists(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        out.append((path, obj, len(flatten_numbers(obj))))
        for v in obj:
            out.extend(_lists(v, f"{path}[]"))
    return out


def count_numbers(obj: Any) -> int:
    return len(flatten_numbers(obj))


def compact(section: dict[str, Any], max_numbers: int = MAX_NUMBERS) -> dict[str, Any]:
    """The section as an agent reads it, with ``left_out`` saying what is not shown."""
    left_out: dict[str, str] = {}
    out = _shrink(section, "", left_out)
    while count_numbers(out) > max_numbers:
        cands = [(p, lst, n) for p, lst, n in _lists(out) if len(lst) > 1 and n > 0]
        if not cands:
            break
        path, lst, _ = max(cands, key=lambda c: c[2])
        before = len(lst)
        del lst[max(1, before // 2) :]
        was = left_out.get(path)
        total = was.split(" of ")[-1] if was and " of " in was else str(before)
        left_out[path] = f"first {len(lst)} of {total}"
    if count_numbers(out) > max_numbers:
        # Numbers outside any list: none of the sections has this many, but the cap holds.
        return {
            "left_out": {"": f"more than {max_numbers} numbers outside any list"},
            "error": "This section is too large to read here.",
        }
    if left_out:
        out["left_out"] = left_out
    return dict(out)
