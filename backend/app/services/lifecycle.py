"""Pieces every lifecycle answer shares: the number shape, dates as numbers, `meta`.

Every section answer is ``{data, meta}`` (docs/lifecycle-api.md). Numbers are
built with ``core.quantity.Quantity``, which refuses a number with no margin
and no reason, and serialised here into the contract's ``Quantity`` shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import ENGINES
from app.core import quantity
from app.core.quantity import Provenance, Quantity, Share

#: Half the span a published date of each precision covers, seconds.
HALF_SPAN_S: dict[str, float] = {
    "minute": 30.0,
    "day": 43_200.0,
    "month": 15.22 * 86_400.0,
    "quarter": 45.66 * 86_400.0,
    "year": 182.62 * 86_400.0,
}

EPOCH_UNIT = "s since epoch"


def q(x: Quantity) -> dict[str, Any]:
    """The contract's ``Quantity``: every key present, nulls where not used."""
    return {
        "value": x.value,
        "unit": x.unit,
        "provenance": x.provenance,
        "pm": x.pm,
        "lo": x.lo,
        "hi": x.hi,
        "factor": x.factor,
        "open": x.open,
        "no_margin_reason": x.no_margin_reason,
        "missing_reason": x.missing_reason,
        "source": x.source,
    }


def share(s: Share) -> dict[str, Any]:
    return {"k": s.k, "n": s.n, "lo": s.lo, "hi": s.hi, "checked": s.checked}


def missing(unit: str, reason: str, *, provenance: Provenance = "computed") -> dict[str, Any]:
    return q(quantity.missing(unit, reason, provenance=provenance))


def parse_time(text: str) -> datetime:
    t = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(t) if "T" in t else datetime.fromisoformat(t + "T00:00:00+00:00")
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def published_date(date: dict[str, Any], source: str) -> dict[str, Any]:
    """A published date (with its precision) as a time number with its span as the margin.

    "March 2025" is the middle of March plus or minus half a month; a
    day-precision date is midday plus or minus twelve hours.
    """
    start = parse_time(date["date"])
    half = HALF_SPAN_S.get(date["precision"], HALF_SPAN_S["year"])
    mid = start if date["precision"] == "minute" else start + timedelta(seconds=half)
    return q(
        Quantity(
            value=mid.timestamp(),
            unit=EPOCH_UNIT,
            provenance="published",
            pm=half,
            source=source,
        )
    )


def entered_date(on: str, who: str) -> dict[str, Any]:
    t = parse_time(on)
    return q(
        Quantity(
            value=(t + timedelta(hours=12)).timestamp() if "T" not in on else t.timestamp(),
            unit=EPOCH_UNIT,
            provenance="entered",
            pm=43_200.0 if "T" not in on else 60.0,
            source=who,
        )
    )


def source_ref(
    name: str,
    url: str | None = None,
    *,
    issued_at: datetime | None = None,
    fetched_at: datetime | None = None,
    licence: str | None = None,
    snapshot_id: int | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "url": url,
        "issued_at": issued_at,
        "fetched_at": fetched_at,
        "licence": licence,
        "snapshot_id": snapshot_id,
    }


def meta(
    *,
    engines: tuple[str, ...],
    sources: list[dict[str, Any]],
    parts: list[tuple[str, str]],
    stale: bool = False,
    compute_ms: float | None = None,
    computed_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "computed_at": computed_at or datetime.now(UTC),
        "uncertainty": {
            "kind": "composite",
            "parts": [{"source": s, "note": n} for s, n in parts],
        },
        "engines": {e: ENGINES[e] for e in engines},
        "sources": sources,
        "stale": stale,
        "compute_ms": compute_ms,
    }


def stretch(start: datetime, end: datetime, open_start: bool, open_end: bool) -> dict[str, Any]:
    return {"start": start, "end": end, "open_start": open_start, "open_end": open_end}


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def jsonable(obj: Any) -> Any:
    """``obj`` with datetimes as ISO strings, safe for a JSONB column."""
    import orjson

    return orjson.loads(orjson.dumps(obj, option=orjson.OPT_UTC_Z | orjson.OPT_NAIVE_UTC))


def trajectory_edge(name: str, at: datetime, *, ends: bool) -> str:
    """Where the recorded JPL Horizons trajectory of an orbiter stops short of the dates."""
    edge = "ends" if ends else "starts"
    return f"The recorded JPL Horizons trajectory for {name} {edge} {at:%Y-%m-%d}."


def horizons_has_none(name: str, after: datetime) -> str:
    """JPL Horizons itself has no trajectory for the orbiter after this day."""
    return f"JPL Horizons has no trajectory for {name} after {after:%Y-%m-%d}."
