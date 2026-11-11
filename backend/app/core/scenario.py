"""What-if scenarios: the fields, how a value is chosen, and how prompts are read by rules.

Pure: no I/O. A scenario assumes values for the fields a mission's record lacks.
Each value is chosen in one order, and the first that has a value wins:

1. ``you``: typed or said in the prompt;
2. ``published``: on the mission's record;
3. ``live``: fetched for this scenario (done only by the compute worker);
4. ``default``: a named precedent or catalogue value, with its source named.

A field with none of the four is a gap, not a guess: it is left out and said.
Nothing here writes to a mission; a scenario's values live in the scenario.

Assumptions are canonicalised before they are hashed (dates to the day, days and
degrees to 0.5, ids sorted), so two prompts that mean the same thing share one
answer.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

#: The steps a scenario can work out ("ready" is entered by people, never assumed).
SECTIONS: tuple[str, ...] = ("launch", "trip", "landing", "contact", "return")

Basis = Literal["you", "published", "live", "default"]
BASIS_ORDER: tuple[Basis, ...] = ("you", "published", "live", "default")


@dataclass(frozen=True, slots=True)
class FieldSpec:
    id: str
    label: str
    help: str
    kind: Literal["choice", "multi_choice", "date", "number"]
    unit: str | None
    min: float | None
    max: float | None
    sections: tuple[str, ...]


SPECS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "vehicle_id",
        "Launch vehicle",
        "Decides how the launch climbs and where the booster comes down.",
        "choice",
        None,
        None,
        None,
        ("launch", "trip", "return"),
    ),
    FieldSpec(
        "pad_id",
        "Launch pad",
        "Decides the directions a launch may climb in and the weather it faces.",
        "choice",
        None,
        None,
        None,
        ("launch", "return"),
    ),
    FieldSpec(
        "site_id",
        "Landing spot",
        "The place whose sunlight and view of Earth the landing and contact steps use.",
        "choice",
        None,
        None,
        None,
        ("launch", "landing", "contact"),
    ),
    FieldSpec(
        "launch_from",
        "Launch from",
        "The first day launch opportunities are looked for.",
        "date",
        None,
        None,
        None,
        ("launch",),
    ),
    FieldSpec(
        "launch_to",
        "Launch until",
        "The last day launch opportunities are looked for (at most 180 days after the first).",
        "date",
        None,
        None,
        None,
        ("launch",),
    ),
    FieldSpec(
        "landing_date",
        "Landing date",
        "When the lander is on the surface; the surface steps start here.",
        "date",
        None,
        None,
        None,
        ("landing", "contact"),
    ),
    FieldSpec(
        "surface_days",
        "Days on the surface",
        "How long the lander works on the surface after landing.",
        "number",
        "days",
        0.5,
        60.0,
        ("launch", "landing", "contact"),
    ),
    FieldSpec(
        "transfer_type",
        "Transfer to the Moon",
        "The kind of flight from Earth orbit to the Moon.",
        "choice",
        None,
        None,
        None,
        ("launch", "trip"),
    ),
    FieldSpec(
        "sun_el_min_deg",
        "Lowest Sun height at landing",
        "Landing needs the Sun at least this high above the skyline.",
        "number",
        "deg",
        0.0,
        90.0,
        ("launch",),
    ),
    FieldSpec(
        "sun_el_max_deg",
        "Highest Sun height at landing",
        "Landing needs the Sun no higher than this above the skyline.",
        "number",
        "deg",
        0.0,
        90.0,
        ("launch",),
    ),
    FieldSpec(
        "relays",
        "Relays added",
        "Planned relay satellites to add to the mission's own when working out contact.",
        "multi_choice",
        None,
        None,
        None,
        ("contact",),
    ),
)
SPEC_BY_ID: dict[str, FieldSpec] = {s.id: s for s in SPECS}
FIELD_IDS: tuple[str, ...] = tuple(s.id for s in SPECS)

TRANSFER_TYPES: dict[str, str] = {
    "direct": "Direct",
    "phasing_loops": "Phasing loops",
    "low_energy": "Low energy",
}

#: What a step cannot be worked out without. Optional fields are not listed: the
#: step runs without them and says so.
REQUIRED: dict[str, tuple[str, ...]] = {
    "launch": ("vehicle_id", "pad_id", "site_id"),
    "trip": (),
    "landing": ("site_id", "landing_date"),
    "contact": ("site_id", "landing_date"),
    "return": ("vehicle_id",),
}

WHY: dict[str, str] = {
    "vehicle_id": "The launch vehicle is not published.",
    "pad_id": "The launch pad is not published.",
    "site_id": "No landing spot is published.",
    "landing_date": "The landing date is not published to the day.",
}


# ---------------------------------------------------------------------------
# Canonical form
# ---------------------------------------------------------------------------


def _half(x: float) -> float:
    return math.floor(float(x) * 2.0 + 0.5) / 2.0


def canonical_value(field_id: str, value: Any) -> Any:
    """One assumption in canonical form; ``None`` when it has no value."""
    if value is None or value == "" or value == []:
        return None
    spec = SPEC_BY_ID.get(field_id)
    if spec is None:
        raise KeyError(f"unknown assumption field {field_id!r}")
    if spec.kind == "date":
        return str(value)[:10]
    if spec.kind == "number":
        x = _half(float(value))
        if spec.min is not None:
            x = max(spec.min, x)
        if spec.max is not None:
            x = min(spec.max, x)
        return x
    if spec.kind == "multi_choice":
        items = [value] if isinstance(value, str) else list(value)
        return sorted({str(v).strip() for v in items if str(v).strip()})
    return str(value).strip()


def canonical(given: Mapping[str, Any]) -> dict[str, Any]:
    """The assumptions a person set, in canonical form, in a stable order."""
    out: dict[str, Any] = {}
    for fid in FIELD_IDS:
        if fid in given:
            v = canonical_value(fid, given[fid])
            if v is not None:
                out[fid] = v
    unknown = set(given) - set(FIELD_IDS)
    if unknown:
        raise KeyError(f"unknown assumption field(s) {sorted(unknown)}")
    return out


def validate(given: Mapping[str, Any]) -> list[str]:
    """Plain sentences for every value that cannot be used; empty when all can."""
    problems: list[str] = []
    for fid, v in given.items():
        spec = SPEC_BY_ID.get(fid)
        if spec is None:
            problems.append(f"'{fid}' is not something a scenario can assume.")
            continue
        if v is None:
            continue
        if spec.kind == "date":
            try:
                date.fromisoformat(str(v)[:10])
            except ValueError:
                problems.append(f"{spec.label}: '{v}' is not a date (use YYYY-MM-DD).")
        elif spec.kind == "number":
            try:
                x = float(v)
            except (TypeError, ValueError):
                problems.append(f"{spec.label}: '{v}' is not a number.")
                continue
            if (spec.min is not None and x < spec.min) or (spec.max is not None and x > spec.max):
                problems.append(f"{spec.label}: {x:g} is outside {spec.min:g} to {spec.max:g}.")
        elif spec.kind == "multi_choice" and not isinstance(v, list | tuple | str):
            problems.append(f"{spec.label}: give a list.")
    lo, hi = given.get("launch_from"), given.get("launch_to")
    if lo and hi and not problems:
        d0, d1 = date.fromisoformat(str(lo)[:10]), date.fromisoformat(str(hi)[:10])
        if d1 <= d0:
            problems.append("Launch until must be after launch from.")
        elif (d1 - d0).days > 180:
            problems.append("Launch opportunities are worked out over at most 180 days.")
    a, b = given.get("sun_el_min_deg"), given.get("sun_el_max_deg")
    if a is not None and b is not None and not problems and float(b) < float(a):
        problems.append("The highest Sun height must not be below the lowest.")
    return problems


def digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def scenario_key(mission_id: str, sections: Iterable[str], given: Mapping[str, Any]) -> str:
    """The scenario's key: the same mission, steps and canonical assumptions give the same key."""
    return digest(
        {"mission": mission_id, "sections": sorted(set(sections)), "given": canonical(given)}
    )


def scenario_id(key: str) -> str:
    return f"sc-{key[:12]}"


# ---------------------------------------------------------------------------
# Choosing a value
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Candidate:
    """A value on offer from one place, with where it came from."""

    value: Any
    source: str
    url: str | None = None
    fetched_at: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Resolved:
    field: str
    value: Any
    basis: Basis
    source: str | None
    url: str | None
    fetched_at: str | None
    note: str | None


def resolve(
    field_id: str,
    *,
    given: Mapping[str, Any],
    published: Candidate | None,
    live: Candidate | None,
    default: Candidate | None,
) -> Resolved | None:
    """The value for one field and its basis, or ``None`` when there is none (a gap)."""
    v = canonical_value(field_id, given.get(field_id))
    if v is not None:
        return Resolved(field_id, v, "you", None, None, None, None)
    for basis, c in (("published", published), ("live", live), ("default", default)):
        if c is not None and c.value is not None:
            val = canonical_value(field_id, c.value)
            if val is not None:
                return Resolved(
                    field_id,
                    val,
                    basis,  # type: ignore[arg-type]
                    c.source,
                    c.url,
                    c.fetched_at,
                    c.note,
                )
    return None


def missing_for(section: str, have: Iterable[str]) -> list[str]:
    """Required fields of a step that nothing supplies."""
    got = set(have)
    return [f for f in REQUIRED.get(section, ()) if f not in got]


# ---------------------------------------------------------------------------
# Precedents (the default basis)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FlightRow:
    """One mission that has flown, as a precedent."""

    mission_id: str
    name: str
    provider: str | None
    lander: str | None
    when: str
    vehicle_id: str | None
    pad_id: str | None


def _recent(rows: Iterable[FlightRow]) -> list[FlightRow]:
    return sorted(rows, key=lambda r: (r.when, r.mission_id), reverse=True)


def precedents(
    provider: str | None, lander: str | None, rows: Sequence[FlightRow]
) -> list[FlightRow]:
    """Flights of the same lander, then the same provider, newest first within each."""
    same_lander = [r for r in rows if lander and r.lander == lander]
    same_provider = [
        r for r in rows if provider and r.provider == provider and r not in same_lander
    ]
    return _recent(same_lander) + _recent(same_provider)


def default_vehicle(
    provider: str | None, lander: str | None, rows: Sequence[FlightRow]
) -> Candidate | None:
    """The vehicle the provider's (or lander's) last flown mission used, else the most used."""
    for r in precedents(provider, lander, rows):
        if r.vehicle_id:
            who = "the same lander" if lander and r.lander == lander else "the same provider"
            return Candidate(
                r.vehicle_id,
                f"Precedent: {r.name}",
                note=f"{r.name}, the last flown mission of {who}, launched on this vehicle.",
            )
    return _most_used([r.vehicle_id for r in rows], "vehicle", len(rows))


def default_pad(
    vehicle_id: str | None,
    provider: str | None,
    lander: str | None,
    rows: Sequence[FlightRow],
    vehicle_pads: Sequence[str] = (),
) -> Candidate | None:
    """The pad a flown mission on this vehicle used (the provider's first), else the most used."""
    if vehicle_id is None:
        return None
    on_vehicle = [r for r in rows if r.vehicle_id == vehicle_id and r.pad_id]
    for r in precedents(provider, lander, on_vehicle):
        return Candidate(
            r.pad_id,
            f"Precedent: {r.name}",
            note=f"{r.name} launched on this vehicle from this pad.",
        )
    c = _most_used([r.pad_id for r in on_vehicle], "pad for this vehicle", len(on_vehicle))
    if c is not None:
        return c
    if len(vehicle_pads) == 1:
        return Candidate(
            vehicle_pads[0],
            "Launch-site catalogue",
            note="The only pad the catalogue lists for this vehicle.",
        )
    return None


def _most_used(values: Iterable[str | None], what: str, total: int) -> Candidate | None:
    c = Counter(v for v in values if v)
    if not c:
        return None
    best = max(sorted(c), key=lambda k: c[k])
    return Candidate(
        best,
        "Catalogue: most used",
        note=f"The {what} used by most flown missions ({c[best]} of {total}).",
    )


def next_precedent(
    provider: str | None,
    lander: str | None,
    rows: Sequence[FlightRow],
    current: tuple[str | None, str | None],
) -> FlightRow | None:
    """The newest precedent whose vehicle and pad differ from ``current``."""
    for r in precedents(provider, lander, rows) + _recent(rows):
        if r.vehicle_id and r.pad_id and (r.vehicle_id, r.pad_id) != current:
            return r
    return None


# ---------------------------------------------------------------------------
# Dates in the record
# ---------------------------------------------------------------------------


def add_months(d: date, n: int) -> date:
    m0 = d.year * 12 + (d.month - 1) + n
    y, m = divmod(m0, 12)
    return date(y, m + 1, 1)


def month_span(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


# ---------------------------------------------------------------------------
# Reading a prompt by rules
# ---------------------------------------------------------------------------

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name} | {
    name.lower(): i for i, name in enumerate(calendar.month_abbr) if name
}

_NUM = r"(\d+(?:\.\d+)?)"
_CLAUSE_END = r"[;,.]|\bthen\b|\band\b"


@dataclass
class Reading:
    values: dict[str, Any] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: ``model``: read by the AI model. ``rules``: read by the pattern rules here.
    method: Literal["model", "rules"] = "rules"
    interpreted_as: str = ""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _find_named(text: str, options: Mapping[str, str]) -> list[str]:
    """Option ids whose name or id appears in ``text`` (longest names first)."""
    flat = _norm(text)
    hits: list[str] = []
    taken = flat
    for oid, name in sorted(options.items(), key=lambda kv: -len(kv[1])):
        for token in (_norm(name), _norm(oid)):
            if len(token) >= 3 and token in taken:
                hits.append(oid)
                taken = taken.replace(token, "|", 1)
                break
    return hits


def _month_date(clause: str, today: date) -> tuple[date, bool] | None:
    """A month named in ``clause`` as ``(first day, year_was_said)``; with no year, the next one."""
    pattern = re.compile(
        r"\b("
        + "|".join(sorted(_MONTHS, key=len, reverse=True))
        + r")\b\.?(?:\s+(\d{1,2})(?:st|nd|rd|th)?\b)?(?:,?\s+(20\d\d))?",
        re.I,
    )
    for m in pattern.finditer(clause):
        if m.group(1).lower() == "may" and not re.search(
            r"\b(in|by|on|of|until|from)\s+$", clause[: m.start(1)], re.I
        ):
            continue  # the verb, not the month; a month named later still counts
        break
    else:
        return None
    word = m.group(1)
    month = _MONTHS[word.lower()]
    year_said = m.group(3) is not None
    year = int(m.group(3)) if year_said else today.year
    if not year_said and date(year, month, 1) < date(today.year, today.month, 1):
        year += 1
    return date(year, month, 1), year_said


def parse_prompt(
    text: str,
    today: date,
    *,
    vehicles: Mapping[str, str],
    pads: Mapping[str, str],
    relays: Mapping[str, str],
) -> Reading:
    """Turn plain words into the values they name. Reads only what is there: no guessing."""
    r = Reading()
    low = text.lower()

    veh = _find_named(text, vehicles)
    if veh:
        r.values["vehicle_id"] = veh[0]
        if len(veh) > 1:
            r.unresolved.append(
                f"More than one vehicle was named; the first, {vehicles[veh[0]]}, was used."
            )
    pad = _find_named(text, pads)
    if pad:
        r.values["pad_id"] = pad[0]
        if len(pad) > 1:
            r.unresolved.append(
                f"More than one pad was named; the first, {pads[pad[0]]}, was used."
            )
    rel = _find_named(text, relays)
    if rel:
        r.values["relays"] = sorted(rel)

    if re.search(r"\bdirect\b", low):
        r.values["transfer_type"] = "direct"
    elif re.search(r"phasing|loops", low):
        r.values["transfer_type"] = "phasing_loops"
    elif re.search(r"low[- ]energy|ballistic", low):
        r.values["transfer_type"] = "low_energy"

    # Days on the surface.
    for dm in re.finditer(_NUM + r"\s*(?:-?\s*)?(?:earth\s+)?days?\b", low):
        # Only the words of the same clause say what the days are for.
        tail = re.split(_CLAUSE_END, low[dm.end() : dm.end() + 40])[0]
        head = re.split(_CLAUSE_END, low[max(0, dm.start() - 40) : dm.start()])[-1]
        if re.search(r"surface|stay|operat|on the moon|lunar day|work", tail + head):
            r.values["surface_days"] = float(dm.group(1))
            break
        if re.search(r"\b(flight|transit|cruise|coast)\b", tail + head):
            continue
        r.unresolved.append(
            f"'{dm.group(0)}' was not clearly days on the surface, so it was not used."
        )

    # Sun height.
    sm = re.search(r"sun[^.]{0,30}?(?:at least|above|min(?:imum)?|over)\s*" + _NUM, low)
    if sm:
        r.values["sun_el_min_deg"] = float(sm.group(1))
    sm = re.search(r"sun[^.]{0,30}?(?:at most|below|max(?:imum)?|under)\s*" + _NUM, low)
    if sm:
        r.values["sun_el_max_deg"] = float(sm.group(1))

    # Dates, clause by clause: "launch ... March", "land ... Q4 2027".
    for clause in re.split(r"[;,]|\band\b|\bthen\b", text, flags=re.I):
        cl = clause.lower()
        iso = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", clause)
        got: tuple[date, date, str] | None = None
        if iso:
            d = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            got = (d, d, f"{d.isoformat()}")
        else:
            q = re.search(r"\bq([1-4])\s*(20\d\d)\b", cl)
            if q:
                first = date(int(q.group(2)), (int(q.group(1)) - 1) * 3 + 1, 1)
                got = (
                    first,
                    add_months(first, 3) - timedelta(days=1),
                    f"Q{q.group(1)} {q.group(2)}",
                )
            else:
                md = _month_date(clause, today)
                if md:
                    first, said = md
                    a, b = month_span(first.year, first.month)
                    nm = calendar.month_name[first.month]
                    got = (a, b, f"{nm} {first.year}")
                    if not said:
                        r.notes.append(
                            f"'{nm}' with no year was read as {nm} {first.year}, the next one."
                        )
        if got is None:
            continue
        a, b, label = got
        if re.search(r"\bland", cl):
            r.values["landing_date"] = a.isoformat()
            if a != b and not iso:
                r.notes.append(f"A landing in {label} was taken as its first day, {a.isoformat()}.")
        elif re.search(r"launch|lift|liftoff|fly|flies", cl):
            r.values["launch_from"], r.values["launch_to"] = a.isoformat(), b.isoformat()
        else:
            r.unresolved.append(
                f"'{clause.strip()}' names a date but not whether it is the launch or the landing."
            )
    return r


# ---------------------------------------------------------------------------
# Names, phases and sentences
# ---------------------------------------------------------------------------

SECTION_LABELS: dict[str, str] = {
    "launch": "Launch opportunities",
    "trip": "Trip",
    "landing": "Surface",
    "contact": "Contact",
    "return": "Return",
}


def display(field_id: str, value: Any, names: Mapping[str, Mapping[str, str]]) -> str:
    """A value in words: a vehicle's name, a date as written, '14 days'."""
    if value is None:
        return "not set"
    spec = SPEC_BY_ID[field_id]
    if spec.kind == "date":
        d = datetime.fromisoformat(str(value)[:10]).replace(tzinfo=UTC)
        return f"{d.day} {d.strftime('%b %Y')}"
    if spec.kind == "number":
        return f"{float(value):g} {spec.unit}" if spec.unit else f"{float(value):g}"
    if field_id == "transfer_type":
        return TRANSFER_TYPES.get(str(value), str(value))
    cat = {
        "vehicle_id": "vehicles",
        "pad_id": "pads",
        "site_id": "sites",
        "relays": "relays",
    }.get(field_id)
    lookup = names.get(cat or "", {})
    if isinstance(value, list):
        return ", ".join(lookup.get(str(v), str(v)) for v in value)
    return lookup.get(str(value), str(value))


def scenario_name(given: Mapping[str, Any], names: Mapping[str, Mapping[str, str]]) -> str:
    parts = []
    if "vehicle_id" in given:
        parts.append(display("vehicle_id", given["vehicle_id"], names))
    if "pad_id" in given:
        parts.append("from " + display("pad_id", given["pad_id"], names))
    if "landing_date" in given:
        parts.append("landing " + display("landing_date", given["landing_date"], names))
    return " ".join(parts) if parts else "Scenario"


def phases(sections: Sequence[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {"id": "inputs", "label": "Checking live sources", "state": "pending", "detail": None}
    ]
    out += [
        {"id": s, "label": SECTION_LABELS[s], "state": "pending", "detail": None}
        for s in SECTIONS
        if s in sections
    ]
    return out


def failed_phases(phases: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The steps of a stored scenario that could not be worked out."""
    return [p for p in phases if p.get("state") == "failed"]


def outcome(phases: Sequence[Mapping[str, Any]], message: str) -> tuple[str, str]:
    """``(status, message)`` for a finished scenario, honest about steps that failed.

    The status vocabulary has no "partly done", so: some steps failed but more worked
    gives ``done`` with a message that names the failed ones; when the failed steps
    outnumber the worked ones the scenario is ``failed``.
    """
    bad = failed_phases(phases)
    if not bad:
        return "done", message
    ok = sum(1 for p in phases if p.get("state") == "done")
    names = ", ".join(str(p.get("label", p.get("id"))).lower() for p in bad)
    if len(bad) > ok:
        return "failed", f"Could not be worked out: {names}."
    return "done", f"Worked out, except {names}, which could not be."
