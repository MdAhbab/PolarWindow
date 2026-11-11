"""Reading a mission document into the project form, with evidence for every field.

Two readers fill the same draft:

* **the model** (a key is configured): the file goes to Gemini (a PDF as its
  own bytes, anything else as text) with a response schema of the form and a
  quote per field. Every value is then checked against the file's own text
  (:func:`verify`), in the spirit of ``guards.py``: a quote that is not in the
  file drops its value; a date, number or name that its quote does not contain
  is dropped or brought down to what the quote does say.
* **the rules** (no key, offline, or the model did not answer): dates in the
  common spellings with their precision, coordinates, masses and durations
  next to the words that name them, and names from the catalogues (vehicles,
  pads, relays) and the missions (providers, landers, sites).

Nothing is guessed. A field the reader looked for and did not find is
``not_found`` and stays empty. Pure apart from the model call: no database
(the caller passes the names to look for in a :class:`Lexicon`).
"""

from __future__ import annotations

import bisect
import json
import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents import base
from app.agents.tools import Session
from app.services.agent_log import AgentRunRecord, record_run

log = logging.getLogger(__name__)

Confidence = Literal["stated", "inferred", "not_found"]
Precision = Literal["second", "minute", "day", "month", "quarter", "year"]

#: Every form field a reader looks for, as dotted paths into ProjectIn.
LOOKED_FOR: tuple[str, ...] = (
    "name",
    "provider",
    "lander",
    "vehicle_name",
    "task_order",
    "status",
    "target",
    "target.site_id",
    "target.name",
    "target.lat_deg",
    "target.lon_deg",
    "launch.date",
    "landing.date",
    "end_of_mission.date",
    "planned_surface_days",
    "lifecycle.vehicle_id",
    "lifecycle.pad_id",
    "lifecycle.transfer_type",
    "lifecycle.flight_days",
    "lifecycle.mass_kg",
    "lifecycle.relays",
    "lifecycle.lunar_orbit_days",
    "lifecycle.sun_el_min_deg",
    "lifecycle.sun_el_max_deg",
    "lifecycle.bands",
    "lifecycle.ground_stations",
    "lifecycle.returns",
    "payloads",
    "notes",
)

#: One reading may take this long in all, however long the chain is (the request must not
#: hang), and no single model may hold it for more than ``MODEL_TIMEOUT_S``: the first
#: models of a long chain can be slow or not served to this key, so at least two or three
#: models get their turn. Under ``MODEL_MIN_S`` left, no new model is started.
EN_DASH, EM_DASH = chr(0x2013), chr(0x2014)
MODEL_BUDGET_S = 70.0
MODEL_TIMEOUT_S = 25.0
MODEL_MIN_S = 5.0
#: Room for the whole form with its quotes. With the agents' 2048 a thinking model spent
#: the cap on reasoning and the form came back cut off after a few fields.
MODEL_MAX_OUTPUT_TOKENS = 8192

EVIDENCE_MAX = 240
#: Most characters of the file's text handed to the model.
MODEL_TEXT_MAX = 60_000

# ---------------------------------------------------------------------------
# The document and the names to look for
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Doc:
    """The file's text as numbered units: ``(page, line)`` for a PDF, else ``(line, line)``."""

    lines: tuple[tuple[int, str], ...]
    paged: bool = False

    @property
    def text(self) -> str:
        return "\n".join(t for _, t in self.lines)

    @classmethod
    def from_text(cls, text: str) -> Doc:
        return cls(tuple((i, line) for i, line in enumerate(text.splitlines(), 1)))

    @classmethod
    def from_pages(cls, pages: list[str]) -> Doc:
        return cls(
            tuple((p, line) for p, page in enumerate(pages, 1) for line in page.splitlines()),
            paged=True,
        )


@dataclass(frozen=True, slots=True)
class Named:
    """A catalogue record and the spellings that name it in prose."""

    id: str
    label: str
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SiteName:
    id: str
    name: str
    lat_deg: float
    lon_deg: float


@dataclass(frozen=True, slots=True)
class Lexicon:
    vehicles: tuple[Named, ...] = ()
    pads: tuple[Named, ...] = ()
    relays: tuple[Named, ...] = ()
    providers: tuple[str, ...] = ()
    landers: tuple[str, ...] = ()
    sites: tuple[SiteName, ...] = ()


def vehicle_names(vid: str, name: str) -> Named:
    """'Falcon 9 Block 5' is also 'Falcon 9'; 'Vulcan Centaur' is also 'Vulcan'."""
    aliases = {name, re.sub(r"\s+Block\s+\d+$", "", name), vid.replace("-", " ")}
    if name.endswith(" Centaur"):
        aliases.add(name.removesuffix(" Centaur"))
    return Named(vid, name, tuple(sorted(aliases, key=len, reverse=True)))


def pad_names(pid: str, name: str) -> Named:
    """'Space Launch Complex 40' is also 'SLC-40'; 'Launch Complex 39A' is also 'LC-39A'."""
    aliases = {name}
    m = re.fullmatch(r"(Space )?Launch Complex (\w+)", name)
    if m:
        short = "SLC" if m.group(1) else "LC"
        num = m.group(2)
        aliases |= {f"{short}-{num}", f"{short} {num}", f"{short}{num}", f"Pad {num}"}
    return Named(pid, name, tuple(sorted(aliases, key=len, reverse=True)))


def plain_names(rid: str, name: str) -> Named:
    return Named(rid, name, tuple(sorted({name, rid.replace("-", " ")}, key=len, reverse=True)))


def _alias_re(alias: str) -> re.Pattern[str]:
    body = re.escape(alias).replace(r"\ ", r"[\s-]*").replace(r"\-", r"[\s-]*")
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", re.IGNORECASE)


# ---------------------------------------------------------------------------
# One reading of one field
# ---------------------------------------------------------------------------


@dataclass
class Found:
    path: str
    value: Any
    confidence: Confidence
    evidence: str | None
    page: int | None
    note: str | None = None


@dataclass
class Reading:
    """What a reader found: the draft, one entry per field looked for, and warnings."""

    draft: dict[str, Any]
    fields: dict[str, dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


def _quote(line: str, start: int = 0, end: int | None = None) -> str:
    """The line, or the ~240 characters of it around ``start:end``."""
    text = " ".join(line.split())
    if len(text) <= EVIDENCE_MAX:
        return text
    end = len(line) if end is None else end
    mid = (start + end) // 2
    lo = max(0, mid - EVIDENCE_MAX // 2)
    return line[lo : lo + EVIDENCE_MAX].strip()


def assemble(found: list[Found], warnings: list[str]) -> Reading:
    """The draft and one ``fields`` entry per path in ``LOOKED_FOR``."""
    draft: dict[str, Any] = {"name": ""}
    fields: dict[str, dict[str, Any]] = {}
    for f in found:
        if f.path in fields:
            continue
        fields[f.path] = {
            "confidence": f.confidence,
            "evidence": f.evidence,
            "page": f.page,
            "note": f.note,
        }
        if f.confidence == "not_found" or f.value is None:
            continue
        if f.path.endswith(".date"):
            draft[f.path.removesuffix(".date")] = f.value
        elif f.path.startswith("lifecycle."):
            draft.setdefault("lifecycle", {})[f.path.removeprefix("lifecycle.")] = f.value
        else:
            draft[f.path] = f.value
    target = draft.get("target")
    if isinstance(target, dict) and "target" in fields:
        for sub in ("site_id", "name", "lat_deg", "lon_deg"):
            if target.get(sub) is not None:
                fields.setdefault(f"target.{sub}", dict(fields["target"]))
    for path in LOOKED_FOR:
        fields.setdefault(
            path,
            {
                "confidence": "not_found",
                "evidence": None,
                "page": None,
                "note": "The file does not say this.",
            },
        )
    return Reading(draft=draft, fields=fields, warnings=warnings)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTHS = {
    name: i
    for i, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ORDINAL_Q = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3}

_DATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "iso_time",
        re.compile(
            r"\b(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\s*"
            r"(Z|UTC|GMT|\+00:?00)(?![\w+-])",
            re.IGNORECASE,
        ),
    ),
    ("iso_day", re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")),
    (
        "d_month_y",
        re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})\.?,?\s+(\d{{4}})\b", re.I),
    ),
    (
        "month_d_y",
        re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I),
    ),
    ("month_y", re.compile(rf"\b({_MON})\.?,?\s+(\d{{4}})\b", re.I)),
    ("q_y", re.compile(r"\b(?:Q([1-4])|([1-4])Q)\s*(?:of\s+)?(?:CY|FY)?\s*(\d{4})\b", re.I)),
    (
        "quarter_y",
        re.compile(
            r"\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?(\d{4})\b", re.I
        ),
    ),
    ("year", re.compile(r"(?<![\w-])((?:19|20)\d{2})(?![\w-])")),
)


@dataclass(frozen=True, slots=True)
class DateHit:
    start: int
    end: int
    date: str
    precision: Precision
    phrase: str

    def at(self) -> datetime:
        t = self.date.replace("Z", "+00:00")
        return datetime.fromisoformat(t if "T" in t else t + "T00:00:00+00:00")


def _day(y: int, m: int, d: int) -> str | None:
    try:
        return datetime(y, m, d, tzinfo=UTC).strftime("%Y-%m-%d")
    except ValueError:
        return None


def find_dates(text: str) -> list[DateHit]:
    """Every date in ``text`` with its precision, most precise spelling winning an overlap."""
    hits: list[DateHit] = []

    def free(a: int, b: int) -> bool:
        return all(b <= h.start or a >= h.end for h in hits)

    for kind, pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            if not free(m.start(), m.end()):
                continue
            g = m.groups()
            date: str | None = None
            precision: Precision = "day"
            if kind == "iso_time":
                day = _day(int(g[0]), int(g[1]), int(g[2]))
                hh, mm = int(g[3]), int(g[4])
                if day is None or hh > 23 or mm > 59 or (g[5] is not None and int(g[5]) > 59):
                    continue
                if g[5] is not None:
                    date, precision = f"{day}T{hh:02d}:{mm:02d}:{int(g[5]):02d}Z", "second"
                else:
                    date, precision = f"{day}T{hh:02d}:{mm:02d}:00Z", "minute"
            elif kind == "iso_day":
                date = _day(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "d_month_y":
                date = _day(int(g[2]), _MONTHS[g[1].lower()], int(g[0]))
            elif kind == "month_d_y":
                date = _day(int(g[2]), _MONTHS[g[0].lower()], int(g[1]))
            elif kind == "month_y":
                date, precision = f"{int(g[1]):04d}-{_MONTHS[g[0].lower()]:02d}-01", "month"
            elif kind == "q_y":
                q = int(g[0] or g[1])
                date, precision = f"{int(g[2]):04d}-{(q - 1) * 3 + 1:02d}-01", "quarter"
            elif kind == "quarter_y":
                q = _ORDINAL_Q.get(g[0].lower(), 4)
                date, precision = f"{int(g[1]):04d}-{(q - 1) * 3 + 1:02d}-01", "quarter"
            else:
                date, precision = f"{int(g[0]):04d}-01-01", "year"
            if date is None:
                continue
            phrase = m.group(0).strip()
            if kind == "year":
                lead = re.search(r"(?:early|mid|late|end of|by|in)[\s-]*$", text[: m.start()], re.I)
                if lead:
                    phrase = text[lead.start() : m.end()].strip()
            hits.append(DateHit(m.start(), m.end(), date, precision, phrase))
    return sorted(hits, key=lambda h: h.start)


_ORDER = ("year", "quarter", "month", "day", "minute", "second")


def _covers(coarse: DateHit, date: str, precision: str) -> bool:
    """Whether ``coarse`` (at its own precision) contains the date ``date``."""
    a = coarse.at()
    t = datetime.fromisoformat(
        date.replace("Z", "+00:00") if "T" in date else date + "T00:00:00+00:00"
    )
    if _ORDER.index(coarse.precision) > _ORDER.index(precision):
        return False
    if coarse.precision == "year":
        return a.year == t.year
    if coarse.precision == "quarter":
        return a.year == t.year and (a.month - 1) // 3 == (t.month - 1) // 3
    if coarse.precision == "month":
        return (a.year, a.month) == (t.year, t.month)
    if coarse.precision == "day":
        return a.date() == t.date()
    if coarse.precision == "minute":
        return a.replace(second=0) == t.replace(second=0)
    return a == t


# ---------------------------------------------------------------------------
# Numbers, coordinates
# ---------------------------------------------------------------------------

_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def numbers_in(text: str) -> list[float]:
    return [_num(m.group(1)) for m in re.finditer(rf"(?<![\w.]){_NUM}", text)]


_HEMI = re.compile(
    rf"(?<![\w.]){_NUM}\s*°?\s*([NS])\b[\s,;/]*{_NUM}\s*°?\s*([EW])\b", re.IGNORECASE
)
_LAT = re.compile(r"\blat(?:itude)?\b\s*[:=]?\s*(-?\d{1,2}(?:\.\d+)?)\s*°?\s*([NS]\b)?", re.I)
_LON = re.compile(r"\blon(?:g|gitude)?\b\s*[:=]?\s*(-?\d{1,3}(?:\.\d+)?)\s*°?\s*([EW]\b)?", re.I)


def find_coordinate(doc: Doc) -> Found | None:
    """A latitude and longitude the file states, in either common spelling."""
    for page, line in doc.lines:
        m = _HEMI.search(line)
        if m:
            lat = _num(m.group(1)) * (-1 if m.group(2).upper() == "S" else 1)
            lon = _num(m.group(3))
            lon = lon if m.group(4).upper() == "E" else 360.0 - lon
            if -90 <= lat <= 90 and 0 <= lon <= 360:
                return Found(
                    "target",
                    {"lat_deg": lat, "lon_deg": lon % 360.0},
                    "stated",
                    _quote(line, m.start(), m.end()),
                    page,
                )
    lat_hit = lon_hit = None
    for page, line in doc.lines:
        if lat_hit is None and (m := _LAT.search(line)):
            lat_hit = (page, line, m)
        if lon_hit is None and (m := _LON.search(line)):
            lon_hit = (page, line, m)
    if lat_hit and lon_hit:
        lm, om = lat_hit[2], lon_hit[2]
        lat = float(lm.group(1))
        if lm.group(2) and lm.group(2).upper() == "S":
            lat = -abs(lat)
        lon = float(om.group(1))
        if om.group(2) and om.group(2).upper() == "W":
            lon = -abs(lon)
        if -90 <= lat <= 90 and -180 <= lon <= 360:
            evidence = (
                _quote(lat_hit[1])
                if lat_hit[1] == lon_hit[1]
                else (
                    _quote(lat_hit[1])[: EVIDENCE_MAX // 2]
                    + " … "
                    + _quote(lon_hit[1])[: EVIDENCE_MAX // 2]
                )
            )
            return Found(
                "target", {"lat_deg": lat, "lon_deg": lon % 360.0}, "stated", evidence, lat_hit[0]
            )
    return None


# ---------------------------------------------------------------------------
# The rules reader
# ---------------------------------------------------------------------------

#: "Label: value", "Label = value" or "Label - value" (a hyphen, en or em dash).
_SEP = r"\s*(?::|=|\s[-\u2013\u2014]\s)\s*"


#: Words whose full stop does not end a sentence ("Acme Corp. Lander: X", "Mar. 14").
_ABBREV = frozenset(
    {"inc", "ltd", "corp", "co", "llc", "dr", "st", "no", "mr", "mrs", "ms", "vs", "approx", "est"}
)
_MONTH_ABBREV = frozenset(m for m in _MONTHS if len(m) == 3 and m != "may") | {"sept"}
_BOUNDARY = re.compile(r"[.;]\s+")


def _boundaries(text: str) -> list[int]:
    """Where a new sentence or clause starts: after '. ' or '; ', not after 'Corp.' or 'Mar. 14'."""
    out: list[int] = []
    for m in _BOUNDARY.finditer(text):
        if m.group(0)[0] == ".":
            word = re.search(r"([^\W\d_]+)$", text[: m.start()])
            if word:
                w = word.group(1).lower()
                labelled = re.match(r"[A-Z][\w ]{0,30}:", text[m.end() :])
                if (len(w) == 1 or w in _ABBREV) and not labelled:
                    continue
                if w in _MONTH_ABBREV and text[m.end() : m.end() + 1].isdigit():
                    continue
        out.append(m.end())
    return out


def _segments(line: str) -> list[str]:
    """The line's sentences ("Provider: X. Lander: Y." is two)."""
    cuts = [0, *_boundaries(line), len(line)]
    return [s for a, b in pairwise(cuts) if (s := line[a:b].strip())]


def _labelled(doc: Doc, labels: str) -> tuple[str, int, str] | None:
    """``Label: value`` as a line or as one sentence of a line -> (value, page, sentence)."""
    pat = re.compile(rf"^\W{{0,4}}(?:{labels}){_SEP}(.{{1,200}}?)\s*[.;]?\s*$", re.IGNORECASE)
    for page, line in doc.lines:
        for seg in _segments(line):
            m = pat.match(seg)
            if m and m.group(1).strip():
                return m.group(1).strip(), page, seg
    return None


_LEGAL = r"(?:\s*,?\s*(?:inc|llc|ltd|corp|corporation|co|company|gmbh|ag)\.?)?"


def _fold(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text).strip().casefold()


def _catalogue_name(value: str, names: Sequence[str]) -> str:
    """The catalogue's spelling when ``value`` is one of its names (or one plus 'Inc.')."""
    key = _fold(value)
    for n in names:
        if _fold(n) == key:
            return n
    for n in names:
        if re.fullmatch(rf"{re.escape(n)}{_LEGAL}", value.strip(), re.IGNORECASE):
            return n
    return value


_GENERIC_TITLE = {"mission", "brief", "summary", "overview", "document", "report", "plan"}
_GENERIC_TITLE |= {"notes", "project", "profile", "description", "data", "sheet", "file"}


def _title(doc: Doc) -> Found | None:
    """The file's first line, when it reads as a title and not as a label or a sentence."""
    for page, line in doc.lines:
        text = re.sub(r"^[\s#*_>|-]+|[\s*_|]+$", "", line)
        if not text:
            continue
        words = text.split()
        if (
            len(words) > 8
            or re.search(r"[:=.;!?]", text)
            or not re.search(r"[A-Za-z]{3}", text)
            or find_dates(text)
            or {w.casefold().strip(",") for w in words} <= _GENERIC_TITLE
        ):
            return None
        return Found(
            "name",
            text[:160],
            "inferred",
            _quote(line),
            page,
            "The first line of the file, taken as its title; it is not labelled as the "
            "mission's name. Check it.",
        )
    return None


def _site_label(value: str) -> str | None:
    """A site's name from 'Shackleton rim, near 89.45 S' -> 'Shackleton rim'."""
    dash = rf"\s[-{EN_DASH}{EM_DASH}]\s"
    cut = re.split(rf"[,;(]|\s(?:near|at|about|around)\s|{dash}|\d", value, maxsplit=1)[0]
    cut = cut.strip(" -:" + EN_DASH + EM_DASH)
    if not re.search(r"[A-Za-z]{3}", cut) or re.match(r"(?:lat|lon)", cut, re.IGNORECASE):
        return None
    return cut


def _mentions(
    doc: Doc, alias_sets: Sequence[tuple[Any, Sequence[str]]]
) -> list[tuple[Any, int, str, int, int]]:
    """Every (key, page, line, start, end) where one of a key's aliases appears."""
    out: list[tuple[Any, int, str, int, int]] = []
    compiled = [(key, [_alias_re(a) for a in aliases]) for key, aliases in alias_sets]
    for page, line in doc.lines:
        for key, pats in compiled:
            for p in pats:
                m = p.search(line)
                if m:
                    out.append((key, page, line, m.start(), m.end()))
                    break
    # "Shackleton" inside "Shackleton rim" is the longer name, not a second record.
    return [
        h
        for h in out
        if not any(
            o[2] == h[2] and (o[3], o[4]) != (h[3], h[4]) and o[3] <= h[3] and h[4] <= o[4]
            for o in out
        )
    ]


def _one_of(
    path: str,
    hits: list[tuple[Any, int, str, int, int]],
    label_of: dict[Any, str],
    context: str,
    warnings: list[str],
    what: str,
) -> Found:
    """The one record the file names; ``not_found`` (and a warning) when it names several."""
    distinct = list(dict.fromkeys(h[0] for h in hits))
    if not distinct:
        return Found(path, None, "not_found", None, None, "The file names none from the catalogue.")
    if len(distinct) > 1:
        names = ", ".join(label_of[k] for k in distinct)
        warnings.append(f"The file names more than one {what} ({names}); none was chosen.")
        return Found(path, None, "not_found", None, None, f"The file names more than one: {names}.")
    key, page, line, a, b = next(h for h in hits if h[0] == distinct[0])
    stated = any(re.search(context, h[2], re.IGNORECASE) for h in hits if h[0] == key)
    return Found(
        path,
        key,
        "stated" if stated else "inferred",
        _quote(line, a, b),
        page,
        None if stated else f"The only {what} the file names; it does not say so in those words.",
    )


_DATE_LABELS: dict[str, str] = {
    "launch.date": r"\blaunch(?:es|ed|ing)?\b|\blift[- ]?off\b",
    "landing.date": r"\blanding\b|\blands?\b|\btouch[- ]?down\b",
    "end_of_mission.date": (
        r"\bend of (?:the )?mission\b|\bmission end\b|\bend of (?:surface )?operations\b"
    ),
}
_NOT_A_DATE_LINE: dict[str, str] = {
    "launch.date": r"\blaunch (?:vehicle|pad|site|complex|provider|services?)\b",
    "landing.date": r"\blanding (?:site|ellipse|zone|spot|area|target|legs?|accuracy)\b",
    "end_of_mission.date": r"$^",
}


_CHAINED = re.compile(r"[\s,/&]*(?:and|or)?[\s,/&]*", re.IGNORECASE)


def _cues(line: str) -> list[tuple[int, int, str]]:
    """Every launch / landing / end-of-mission cue in the line: (start, end, date path)."""
    out: list[tuple[int, int, str]] = []
    for key, pattern in _DATE_LABELS.items():
        for m in re.finditer(pattern, line, re.IGNORECASE):
            if re.match(_NOT_A_DATE_LINE[key], line[m.start() :], re.IGNORECASE):
                continue
            out.append((m.start(), m.end(), key))
    return sorted(out)


def bound_dates(line: str) -> dict[str, list[DateHit]]:
    """Each date in the line bound to the cue that owns it, or to none.

    A date belongs to the nearest cue before it in its own clause (a full stop or
    semicolon ends a clause), with no other date in between. Two cues side by side
    ("launch and landing: 14 March 2028") own nothing. A date with no cue before it
    belongs to the one cue after it only when it is the clause's only date.
    """
    hits = find_dates(line)
    cues = _cues(line)
    bounds = _boundaries(line)
    out: dict[str, list[DateHit]] = {k: [] for k in _DATE_LABELS}
    for i, h in enumerate(hits):
        start = max([0, *(b for b in bounds if b <= h.start)])
        end = min([len(line), *(b for b in bounds if b > h.start)])
        lo = max(start, hits[i - 1].end) if i else start
        before = [c for c in cues if lo <= c[0] and c[1] <= h.start]
        if before:
            if (
                len(before) > 1
                and before[-2][2] != before[-1][2]
                and _CHAINED.fullmatch(line[before[-2][1] : before[-1][0]])
            ):
                continue
            out[before[-1][2]].append(h)
            continue
        alone = sum(1 for o in hits if start <= o.start < end) == 1
        after = {c[2] for c in cues if h.end <= c[0] < end}
        if alone and len(after) == 1:
            out[after.pop()].append(h)
    return out


def _date_field(doc: Doc, path: str, warnings: list[str]) -> Found:
    seen: list[tuple[DateHit, int, str]] = []
    for page, line in doc.lines:
        seen.extend((h, page, line) for h in bound_dates(line)[path])
    if not seen:
        return Found(path, None, "not_found", None, None, "No date is given next to these words.")
    first, page, line = seen[0]
    others = {h.date for h, _, _ in seen[1:]} - {first.date}
    if others:
        word = path.removesuffix(".date").replace("_", " ")
        warnings.append(
            f"The file gives more than one {word} date ({first.phrase}, and "
            f"{len(others)} other); the first is used. Check it."
        )
    return Found(
        path,
        {"date": first.date, "precision": first.precision, "as_published": first.phrase},
        "stated",
        _quote(line, first.start, first.end),
        page,
    )


def _number_field(
    doc: Doc, path: str, patterns: list[re.Pattern[str]], note: str | None = None
) -> Found:
    for page, line in doc.lines:
        for pat in patterns:
            m = pat.search(line)
            if m:
                return Found(
                    path, _num(m.group(1)), "stated", _quote(line, m.start(), m.end()), page, note
                )
    return Found(path, None, "not_found", None, None, "No value is given next to these words.")


_MASS = re.compile(
    rf"(?<![\w.]){_NUM}\s*(kg|kilograms?|t|tonnes?|metric tons?|lbs?|pounds?)\b", re.IGNORECASE
)
_MASS_WORDS = re.compile(r"\bmass\b|\bweigh", re.IGNORECASE)
_TO_KG = {
    "kg": 1.0,
    "kilogram": 1.0,
    "kilograms": 1.0,
    "t": 1000.0,
    "tonne": 1000.0,
    "tonnes": 1000.0,
    "metric ton": 1000.0,
    "metric tons": 1000.0,
    "lb": 0.45359237,
    "lbs": 0.45359237,
    "pound": 0.45359237,
    "pounds": 0.45359237,
}


def _mass(doc: Doc) -> Found:
    for page, line in doc.lines:
        if not _MASS_WORDS.search(line):
            continue
        m = _MASS.search(line)
        if not m:
            continue
        unit = m.group(2).lower()
        factor = _TO_KG.get(unit, 1.0)
        value = _num(m.group(1)) * factor
        if factor == 1.0:
            return Found(
                "lifecycle.mass_kg", value, "stated", _quote(line, m.start(), m.end()), page
            )
        return Found(
            "lifecycle.mass_kg",
            round(value, 3),
            "inferred",
            _quote(line, m.start(), m.end()),
            page,
            f"The file gives {m.group(0).strip()}; converted to kilograms.",
        )
    return Found("lifecycle.mass_kg", None, "not_found", None, None, "No mass is given.")


_SURFACE_DAYS = [
    re.compile(rf"{_NUM}\s*(?:earth[\s-]+)?days?\s+(?:on|at)\s+the\s+(?:lunar\s+)?surface", re.I),
    re.compile(
        rf"surface\s+(?:operations?|mission|duration|stay|lifetime)\D{{0,30}}?{_NUM}\s*(?:earth[\s-]+)?days?\b",
        re.I,
    ),
]
_FLIGHT_DAYS = [
    re.compile(
        rf"{_NUM}\s*[-\s]?days?\s+(?:of\s+)?(?:transit|cruise|flight|trip|journey)\b(?!\s+on)", re.I
    ),
    re.compile(rf"(?:transit|cruise|flight time|trip)\D{{0,30}}?{_NUM}\s*days?\b", re.I),
    re.compile(rf"{_NUM}\s*days?\s+to\s+(?:reach\s+)?the\s+moon", re.I),
]
_TRANSFER = (
    ("low_energy", re.compile(r"\blow[\s-]energy\b|\bballistic lunar transfer\b|\bBLT\b", re.I)),
    ("phasing_loops", re.compile(r"\bphasing (?:loops?|orbits?)\b", re.I)),
    (
        "direct",
        re.compile(r"\bdirect (?:transfer|trajectory|trans-?lunar|injection|insertion)\b", re.I),
    ),
)
_TASK_ORDER = re.compile(
    r"\btask order\b\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z0-9][\w-]{0,19})", re.I
)
_BULLET = re.compile(r"^\s*(?:[-*•▪◦]|\d{1,2}[.)])\s+(.{2,200}?)\s*$")


def _payloads(doc: Doc) -> tuple[list[dict[str, Any]], Found]:
    """Payloads named on 'Payload: X' lines, or as a list under a 'Payloads' heading."""
    out: list[dict[str, Any]] = []
    first: tuple[int, str] | None = None
    single = re.compile(rf"^\W{{0,4}}(?:payloads?|instruments?){_SEP}(.{{2,400}}?)\s*$", re.I)
    heading = re.compile(
        r"^\W{0,4}(?:nasa\s+|science\s+)?(?:payloads?|instruments?)\b[^:]{0,40}:?\s*$", re.I
    )
    lines = list(doc.lines)
    i = 0
    while i < len(lines):
        page, line = lines[i]
        m = None
        for seg in _segments(line):
            m = single.match(seg)
            if m:
                out.extend(_payload_items(m.group(1)))
                first = first or (page, seg)
                break
        if m:
            pass
        elif heading.match(line.strip()):
            j = i + 1
            while j < len(lines) and len(out) < 30:
                b = _BULLET.match(lines[j][1])
                if not b:
                    if lines[j][1].strip():
                        break
                    j += 1
                    continue
                out.extend(_payload_items(b.group(1), split=False))
                first = first or lines[j]
                j += 1
            i = j
            continue
        i += 1
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in out:
        if p["name"].lower() not in seen:
            seen.add(p["name"].lower())
            unique.append(p)
    if not unique or first is None:
        return [], Found("payloads", None, "not_found", None, None, "No payload is listed.")
    note = f"{len(unique)} payload{'s' if len(unique) != 1 else ''} named; their types are not set."
    if any(p["purpose"] for p in unique):
        note += " The form has no mass field, so a mass the file states is kept in the purpose."
    return unique, Found("payloads", unique, "stated", _quote(first[1]), first[0], note)


_ARTICLE = re.compile(r"^(?:an?|the)\s+", re.IGNORECASE)
_MASS_PAREN = re.compile(
    rf"\(\s*(?:mass\s*[:=]?\s*)?{_NUM}\s*(kg|kilograms?|t|tonnes?|lbs?|pounds?)\s*\)", re.I
)
_MASS_TAIL = re.compile(
    rf"[,:{EN_DASH}{EM_DASH}-]\s*{_NUM}\s*(kg|kilograms?|lbs?|pounds?)\s*$", re.I
)


def _top_level_split(text: str, seps: str) -> list[str]:
    """Split on any character of ``seps`` that is not inside brackets."""
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in text:
        depth += (ch in "([") - (ch in ")]")
        if ch in seps and depth <= 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _payload_items(text: str, split: bool = True) -> list[dict[str, Any]]:
    """'a neutron spectrometer (4.2 kg) and a laser retroreflector (0.3 kg)' -> two payloads.

    'and' separates two payloads only when the second starts with an article or either
    has a mass in brackets ('neutron and gamma-ray spectrometer' is one).
    """
    pieces: list[str] = []
    for chunk in _top_level_split(text.strip().rstrip("."), ",;") if split else [text]:
        chunk = re.sub(r"^(?:and|&)\s+", "", chunk.strip(), flags=re.IGNORECASE)
        sub = re.split(r"\s+(?:and|&)\s+", chunk, flags=re.IGNORECASE) if split else [chunk]
        merged = [sub[0]]
        for nxt in sub[1:]:
            prev = merged[-1]
            if _ARTICLE.match(nxt) or _MASS_PAREN.search(prev) or _MASS_PAREN.search(nxt):
                merged.append(nxt)
            else:
                merged[-1] = f"{prev} and {nxt}"
        pieces += merged
    items: list[dict[str, Any]] = []
    for piece in pieces:
        phrase: str | None = None
        kg: float | None = None
        m = _MASS_PAREN.search(piece) or _MASS_TAIL.search(piece)
        if m:
            phrase = m.group(0).strip("()[] ,:-" + EN_DASH + EM_DASH).strip()
            kg = round(_num(m.group(1)) * _TO_KG.get(m.group(2).lower(), 1.0), 3)
            piece = (piece[: m.start()] + piece[m.end() :]).strip()
        name = _ARTICLE.sub("", piece).strip(" .,;")
        if len(name) < 2:
            continue
        item: dict[str, Any] = {
            "name": name[:1].upper() + name[1:],
            "instrument_types": [],
            "purpose": None,
        }
        if kg is not None:
            item["purpose"] = f"Mass stated in the file: {kg:g} kg" + (
                "" if phrase and phrase.lower().replace(" ", "") == f"{kg:g}kg" else f" ({phrase})"
            )
        items.append(item)
    return items


_BARE_SITE = re.compile(r"\s*\((?:feature centre|IAU[^)]*)\)\s*$")


def read_rules(doc: Doc, lex: Lexicon) -> Reading:
    """The form filled from what the file says, by pattern rules only."""
    warnings: list[str] = []
    found: list[Found] = []

    def label(path: str, labels: str, max_len: int, names: Sequence[str] = ()) -> Found | None:
        hit = _labelled(doc, labels)
        if hit is None:
            return None
        value, page, line = hit
        return Found(path, _catalogue_name(value, names)[:max_len], "stated", _quote(line), page)

    found.append(
        label("name", r"mission(?: name| brief| title)?|project(?: name)?", 160)
        or _title(doc)
        or Found("name", None, "not_found", None, None, "No line names the mission.")
    )
    prov = label(
        "provider",
        r"provider|clps provider|lander provider|company|prime contractor",
        120,
        lex.providers,
    )
    if prov is None:
        hits = _mentions(doc, [(p, (p,)) for p in lex.providers])
        prov = _one_of(
            "provider",
            hits,
            {p: p for p in lex.providers},
            r"provider|built|deliver|company",
            warnings,
            "provider",
        )
    found.append(prov)
    lander = label("lander", r"lander(?: name)?|lander type", 120, lex.landers)
    if lander is None:
        hits = _mentions(doc, [(n, (n,)) for n in lex.landers])
        lander = _one_of("lander", hits, {n: n for n in lex.landers}, r"lander", warnings, "lander")
    found.append(lander)
    found.append(
        label("vehicle_name", r"spacecraft(?: name)?|vehicle name|lander name", 80)
        or Found("vehicle_name", None, "not_found", None, None, "No line names the spacecraft.")
    )
    to = None
    for page, line in doc.lines:
        m = _TASK_ORDER.search(line)
        if m:
            to = Found(
                "task_order", m.group(1)[:40], "stated", _quote(line, m.start(), m.end()), page
            )
            break
    found.append(
        to or Found("task_order", None, "not_found", None, None, "No task order is given.")
    )

    coord = find_coordinate(doc)
    bare = {s.id: _BARE_SITE.sub("", s.name) for s in lex.sites}
    # "Shackleton rim, east shoulder" is also named by its first part, "Shackleton rim".
    site_aliases = [
        (s.id, tuple(dict.fromkeys((bare[s.id], bare[s.id].split(",")[0].strip()))))
        for s in lex.sites
    ]
    hits = _mentions(doc, site_aliases)
    if coord is not None:
        # The form takes a site or a coordinate, not both: the coordinate stays as the
        # file states it, and a site the file also names is offered, never dropped.
        named = _labelled(doc, r"landing site|target(?: site)?|landing target|site")
        name = _site_label(named[0]) if named else None
        site_ids = list(dict.fromkeys(h[0] for h in hits))
        if len(site_ids) == 1:
            name = bare[site_ids[0]].split(",")[0].strip() if name is None else name
            _, spage, sline, sa, sb = hits[0]
            full = bare[site_ids[0]]
            if _fold(sline[sa:sb]) == _fold(full):
                name = full
            found.append(
                Found(
                    "target.site_id",
                    None,
                    "inferred",
                    _quote(sline, sa, sb),
                    spage,
                    f"The file names {sline[sa:sb]}, which matches the surveyed site {full} "
                    f"({site_ids[0]}), as well as coordinates. The form takes a site or a "
                    "coordinate, not both, so the coordinates are kept as stated and the "
                    "site is offered here.",
                )
            )
        if name:
            coord.value["name"] = name[:160]
        found.append(coord)
    else:
        site_found = _one_of(
            "target",
            hits,
            {s.id: s.name for s in lex.sites},
            r"land|target|site|touch",
            warnings,
            "surveyed site",
        )
        if site_found.value is not None:
            sid = site_found.value
            site_found.value = {"site_id": sid}
            _, _, sline, sa, sb = next(h for h in hits if h[0] == sid)
            if _fold(sline[sa:sb]) != _fold(bare[sid]):
                site_found.confidence = "inferred"
                site_found.note = (
                    f"The file says {sline[sa:sb]}; matched to the surveyed site "
                    f"{bare[sid]} by the first part of its name. Check it."
                )
            else:
                site_found.note = (
                    f"{site_found.note or ''} Matched to a surveyed site by name.".strip()
                )
        found.append(site_found)

    for path in ("launch.date", "landing.date", "end_of_mission.date"):
        found.append(_date_field(doc, path, warnings))
    found.append(_number_field(doc, "planned_surface_days", _SURFACE_DAYS))

    vhits = _mentions(doc, [(v.id, v.aliases) for v in lex.vehicles])
    found.append(
        _one_of(
            "lifecycle.vehicle_id",
            vhits,
            {v.id: v.label for v in lex.vehicles},
            r"launch|rocket|vehicle|aboard|on a",
            warnings,
            "launch vehicle",
        )
    )
    phits = _mentions(doc, [(p.id, p.aliases) for p in lex.pads])
    found.append(
        _one_of(
            "lifecycle.pad_id",
            phits,
            {p.id: p.label for p in lex.pads},
            r"launch|pad|complex|from",
            warnings,
            "launch pad",
        )
    )
    transfer = None
    for page, line in doc.lines:
        for kind, pat in _TRANSFER:
            m = pat.search(line)
            if m:
                transfer = Found(
                    "lifecycle.transfer_type",
                    kind,
                    "stated",
                    _quote(line, m.start(), m.end()),
                    page,
                )
                break
        if transfer:
            break
    found.append(
        transfer
        or Found(
            "lifecycle.transfer_type", None, "not_found", None, None, "The trajectory is not named."
        )
    )
    found.append(_number_field(doc, "lifecycle.flight_days", _FLIGHT_DAYS))
    found.append(_mass(doc))
    rhits = _mentions(doc, [(r.id, r.aliases) for r in lex.relays])
    if rhits:
        ids = list(dict.fromkeys(h[0] for h in rhits))
        _, page, line, a, b = rhits[0]
        found.append(Found("lifecycle.relays", ids, "stated", _quote(line, a, b), page))
    else:
        found.append(
            Found(
                "lifecycle.relays",
                None,
                "not_found",
                None,
                None,
                "No relay from the catalogue is named.",
            )
        )
    _, pay = _payloads(doc)
    found.append(pay)
    return assemble(found, warnings)


# ---------------------------------------------------------------------------
# The model reader
# ---------------------------------------------------------------------------


class _Field(BaseModel):
    model_config = ConfigDict(extra="ignore")

    evidence: str | None = Field(
        default=None, description="The exact words in the file this was read from, copied."
    )
    page: int | None = Field(default=None, description="1-based page (PDF) or line number.")
    confidence: Literal["stated", "inferred"] = "stated"
    note: str | None = Field(default=None, description="Why, when the value is inferred.")


class TextField(_Field):
    value: str | None = None


class NumberField(_Field):
    value: float | None = None


class ListField(_Field):
    values: list[str] = Field(default_factory=list)


class DateField(_Field):
    date: str | None = Field(default=None, description="ISO date or datetime in UTC.")
    precision: Precision | None = None
    as_written: str | None = Field(default=None, description="The date as the file writes it.")


class TargetField(_Field):
    lat_deg: float | None = None
    lon_deg: float | None = Field(default=None, description="Degrees east, 0-360.")
    name: str | None = None
    site_id: str | None = Field(default=None, description="Only an id from the site list.")


InstrumentType = Literal[
    "volatiles",
    "geology_geophysics",
    "heat_flow",
    "radiation_space_weather",
    "exosphere_dust",
    "imaging",
    "landing_navigation",
    "communications",
    "laser_retroreflector",
    "rover_mobility",
    "technology_demo",
    "other",
]


class PayloadReading(_Field):
    name: str
    acronym: str | None = None
    organisation: str | None = None
    instrument_types: list[InstrumentType] = Field(default_factory=list)
    purpose: str | None = None


class ModelReading(BaseModel):
    """The form as the model read it: every value with the words it came from."""

    model_config = ConfigDict(extra="ignore")

    name: TextField = Field(default_factory=TextField)
    provider: TextField = Field(default_factory=TextField)
    lander: TextField = Field(default_factory=TextField)
    vehicle_name: TextField = Field(default_factory=TextField)
    task_order: TextField = Field(default_factory=TextField)
    target: TargetField = Field(default_factory=TargetField)
    launch: DateField = Field(default_factory=DateField)
    landing: DateField = Field(default_factory=DateField)
    end_of_mission: DateField = Field(default_factory=DateField)
    planned_surface_days: NumberField = Field(default_factory=NumberField)
    vehicle_id: TextField = Field(default_factory=TextField)
    pad_id: TextField = Field(default_factory=TextField)
    transfer_type: TextField = Field(default_factory=TextField)
    flight_days: NumberField = Field(default_factory=NumberField)
    mass_kg: NumberField = Field(default_factory=NumberField)
    relays: ListField = Field(default_factory=ListField)
    payloads: list[PayloadReading] = Field(default_factory=list)


SYSTEM = """\
You read a lunar mission document and fill in a project form from it.

For every field, copy into `evidence` the exact words of the document the value
comes from (at most 240 characters, verbatim, no paraphrase) and give its page
(PDF) or line number. If the document does not say a field, leave the value null
and the evidence null. Never guess, never fill a field from general knowledge,
never compute a number the document does not state. A value worked out from what
the document says (for example a mass given in tonnes) is `inferred`, with a note
saying how; everything else is `stated`.

Dates: ISO in UTC, with the precision the document gives (year, quarter, month,
day, minute, second); `as_written` is the date as the document writes it. A
time is UTC only when the document says UTC or Z.

`vehicle_id`, `pad_id`, `relays` and `target.site_id` take ONLY ids from the
lists you are given, and only when the document names that record.
`transfer_type` is one of direct, phasing_loops, low_energy.
"""


class ModelFailed(RuntimeError):
    """The model did not give a reading that could be used."""


#: Curly quotes and the dash family, written as escapes, folded to plain ones.
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_DASHES = re.compile("[\u2010-\u2015\u2212]")


def _norm(text: str) -> str:
    t = text.lower().translate(_QUOTES)
    t = _DASHES.sub("-", t)
    return " ".join(t.split())


class _Located:
    """The file's text, normalised once, to find a quote and its page or line."""

    def __init__(self, doc: Doc) -> None:
        self.doc = doc
        parts: list[str] = []
        self.starts: list[int] = []
        pos = 0
        for _, line in doc.lines:
            n = _norm(line)
            self.starts.append(pos)
            parts.append(n)
            pos += len(n) + 1
        self.joined = " ".join(parts)

    def find(self, quote: str | None) -> int | None:
        """The page or line of ``quote``; None when the file does not contain it."""
        if not quote or not quote.strip():
            return None
        q = _norm(quote).strip(" .…")
        if not q:
            return None
        pieces = [p.strip() for p in re.split(r"\s*(?:\.\.\.|…)\s*", q) if p.strip()]
        idx = -1
        for piece in pieces:
            idx = self.joined.find(piece)
            if idx < 0:
                return None
        first = self.joined.find(pieces[0])
        line_no = max(0, bisect.bisect_right(self.starts, first) - 1)
        return self.doc.lines[line_no][0] if self.doc.lines else None

    def contains(self, words: str) -> bool:
        return bool(words.strip()) and _norm(words) in self.joined


def _dropped(path: str, why: str) -> Found:
    return Found(path, None, "not_found", None, None, why)


NOT_IN_FILE = "The model's quote for this is not in the file's text, so its value was dropped."


def verify(reading: ModelReading, doc: Doc, lex: Lexicon) -> Reading:
    """Keep only what the file's own text supports (no text: everything becomes inferred)."""
    warnings: list[str] = []
    found: list[Found] = []
    loc = _Located(doc)
    checkable = bool(loc.joined.strip())
    if not checkable:
        warnings.append(
            "The file's text could not be read here, so the model's quotes could not be "
            "checked against it: every value is marked as worked out. Check each one."
        )

    def where(f: _Field) -> tuple[bool, int | None]:
        if not checkable:
            return True, f.page
        page = loc.find(f.evidence)
        return page is not None, page

    def conf(f: _Field) -> Confidence:
        return f.confidence if checkable else "inferred"

    def note(f: _Field) -> str | None:
        if checkable:
            return f.note
        return "Read by the model; the file's text was not available to check the quote."

    def text_field(path: str, f: TextField, max_len: int) -> Found:
        if not f.value or not f.value.strip():
            return _dropped(path, "The file does not say this.")
        ok, page = where(f)
        if not ok:
            warnings.append(f"{path}: {NOT_IN_FILE}")
            return _dropped(path, NOT_IN_FILE)
        value = " ".join(f.value.split())[:max_len]
        if checkable and not (loc.contains(value) or _norm(value) in _norm(f.evidence or "")):
            return _dropped(path, "The value is not written in the file, so it was dropped.")
        return Found(path, value, conf(f), (f.evidence or "")[:EVIDENCE_MAX] or None, page, note(f))

    for path, max_len in (
        ("name", 160),
        ("provider", 120),
        ("lander", 120),
        ("vehicle_name", 80),
        ("task_order", 40),
    ):
        found.append(text_field(path, getattr(reading, path), max_len))

    found.append(_verify_target(reading.target, lex, loc, checkable, warnings, where, conf, note))
    for key in ("launch", "landing", "end_of_mission"):
        found.append(
            _verify_date(f"{key}.date", getattr(reading, key), checkable, warnings, where, note)
        )
    for path, f in (
        ("planned_surface_days", reading.planned_surface_days),
        ("lifecycle.flight_days", reading.flight_days),
        ("lifecycle.mass_kg", reading.mass_kg),
    ):
        found.append(_verify_number(path, f, checkable, warnings, where, note))

    def catalogue(path: str, value: str | None, f: _Field, records: tuple[Named, ...]) -> Found:
        if not value:
            return _dropped(path, "The file does not name one from the catalogue.")
        rec = next((r for r in records if r.id == value), None)
        if rec is None:
            return _dropped(path, f"'{value}' is not in the catalogue, so it was dropped.")
        ok, page = where(f)
        if not ok:
            warnings.append(f"{path}: {NOT_IN_FILE}")
            return _dropped(path, NOT_IN_FILE)
        if checkable and not any(_alias_re(a).search(loc.joined) for a in rec.aliases):
            return _dropped(path, f"The file does not name {rec.label}, so it was dropped.")
        return Found(
            path, rec.id, conf(f), (f.evidence or "")[:EVIDENCE_MAX] or None, page, note(f)
        )

    found.append(
        catalogue(
            "lifecycle.vehicle_id", reading.vehicle_id.value, reading.vehicle_id, lex.vehicles
        )
    )
    found.append(catalogue("lifecycle.pad_id", reading.pad_id.value, reading.pad_id, lex.pads))
    tt = (reading.transfer_type.value or "").strip()
    if tt in ("direct", "phasing_loops", "low_energy"):
        ok, page = where(reading.transfer_type)
        found.append(
            Found(
                "lifecycle.transfer_type",
                tt,
                conf(reading.transfer_type),
                (reading.transfer_type.evidence or "")[:EVIDENCE_MAX] or None,
                page,
                note(reading.transfer_type),
            )
            if ok
            else _dropped("lifecycle.transfer_type", NOT_IN_FILE)
        )
    else:
        found.append(_dropped("lifecycle.transfer_type", "The file does not name the trajectory."))
    relays = []
    for rid in reading.relays.values:
        rec = next((r for r in lex.relays if r.id == rid), None)
        if rec and (not checkable or any(_alias_re(a).search(loc.joined) for a in rec.aliases)):
            relays.append(rec.id)
    if relays:
        _, page = where(reading.relays)
        found.append(
            Found(
                "lifecycle.relays",
                relays,
                conf(reading.relays),
                (reading.relays.evidence or "")[:EVIDENCE_MAX] or None,
                page,
                note(reading.relays),
            )
        )
    else:
        found.append(_dropped("lifecycle.relays", "The file names no relay from the catalogue."))

    payloads: list[dict[str, Any]] = []
    first: Found | None = None
    for p in reading.payloads[:60]:
        name = " ".join(p.name.split())
        if not name or (checkable and not loc.contains(name)):
            continue
        payloads.append(
            {
                "name": name[:200],
                "acronym": p.acronym
                if p.acronym and (not checkable or loc.contains(p.acronym))
                else None,
                "organisation": p.organisation
                if p.organisation and (not checkable or loc.contains(p.organisation))
                else None,
                "instrument_types": list(dict.fromkeys(p.instrument_types)),
                "purpose": p.purpose,
            }
        )
        if first is None:
            _, page = where(p)
            first = Found("payloads", None, conf(p), (p.evidence or name)[:EVIDENCE_MAX], page)
    dropped = len(reading.payloads) - len(payloads)
    if dropped > 0:
        warnings.append(
            f"{dropped} payload name(s) the model gave are not in the file and were dropped."
        )
    if payloads and first is not None:
        first.value = payloads
        first.note = (
            f"{len(payloads)} payload{'s' if len(payloads) != 1 else ''} named; "
            "their types and purposes are the model's reading."
        )
        found.append(first)
    else:
        found.append(_dropped("payloads", "The file names no payload."))
    return assemble(found, warnings)


def _verify_target(
    t: TargetField,
    lex: Lexicon,
    loc: _Located,
    checkable: bool,
    warnings: list[str],
    where: Any,
    conf: Any,
    note: Any,
) -> Found:
    if t.lat_deg is not None and t.lon_deg is not None:
        ok, page = where(t)
        if not ok:
            warnings.append(f"target: {NOT_IN_FILE}")
            return _dropped("target", NOT_IN_FILE)
        stated = numbers_in(t.evidence or "") if checkable else []
        if checkable and not (
            _in_numbers(abs(t.lat_deg), stated)
            and (
                _in_numbers(t.lon_deg % 360.0, stated)
                or _in_numbers(360.0 - t.lon_deg % 360.0, stated)
                or _in_numbers(abs(t.lon_deg), stated)
            )
        ):
            return _dropped(
                "target", "The coordinate is not in the quoted words, so it was dropped."
            )
        if not (-90 <= t.lat_deg <= 90):
            return _dropped("target", "The latitude is out of range, so it was dropped.")
        value: dict[str, Any] = {"lat_deg": t.lat_deg, "lon_deg": t.lon_deg % 360.0}
        if t.name and (not checkable or loc.contains(t.name)):
            value["name"] = " ".join(t.name.split())[:160]
        return Found(
            "target", value, conf(t), (t.evidence or "")[:EVIDENCE_MAX] or None, page, note(t)
        )
    if t.site_id:
        site = next((s for s in lex.sites if s.id == t.site_id), None)
        if site is None:
            return _dropped("target", f"'{t.site_id}' is not a surveyed site, so it was dropped.")
        bare = re.sub(r"\s*\((?:feature centre|IAU[^)]*)\)\s*$", "", site.name)
        if checkable and not _alias_re(bare).search(loc.joined):
            return _dropped("target", f"The file does not name {site.name}, so it was dropped.")
        _, page = where(t)
        return Found(
            "target",
            {"site_id": site.id},
            "inferred",
            (t.evidence or "")[:EVIDENCE_MAX] or None,
            page,
            f"Matched to the surveyed site {site.name} by name.",
        )
    return _dropped("target", "The file gives no landing spot.")


def _in_numbers(value: float, numbers: list[float], tol: float = 1e-6) -> bool:
    return any(abs(value - n) <= max(tol, abs(n) * 1e-9) for n in numbers)


def _verify_date(
    path: str, f: DateField, checkable: bool, warnings: list[str], where: Any, note: Any
) -> Found:
    if not f.date or not f.precision:
        return _dropped(path, "The file does not give this date.")
    ok, page = where(f)
    if not ok:
        warnings.append(f"{path}: {NOT_IN_FILE}")
        return _dropped(path, NOT_IN_FILE)
    if not checkable:
        return Found(
            path,
            {"date": f.date, "precision": f.precision, "as_published": f.as_written or f.date},
            "inferred",
            (f.evidence or "")[:EVIDENCE_MAX] or None,
            page,
            note(f),
        )
    try:
        datetime.fromisoformat(f.date.replace("Z", "+00:00"))
    except ValueError:
        return _dropped(path, "The model's date is not a date, so it was dropped.")
    hits = find_dates(f.evidence or "")
    exact = [
        h
        for h in hits
        if _ORDER.index(h.precision) >= _ORDER.index(f.precision)
        and _covers_exact(h, f.date, f.precision)
    ]
    if exact:
        h = exact[0]
        return Found(
            path,
            {
                "date": _cut(f.date, f.precision),
                "precision": f.precision,
                "as_published": f.as_written or h.phrase,
            },
            f.confidence,
            (f.evidence or "")[:EVIDENCE_MAX],
            page,
            f.note,
        )
    coarser = [h for h in hits if _covers(h, f.date, f.precision)]
    if coarser:
        h = max(coarser, key=lambda x: _ORDER.index(x.precision))
        warnings.append(
            f"{path}: the file gives this only as '{h.phrase}'; the date was kept to "
            "that precision."
        )
        return Found(
            path,
            {"date": h.date, "precision": h.precision, "as_published": h.phrase},
            "stated",
            (f.evidence or "")[:EVIDENCE_MAX],
            page,
            f"The file gives this only to the {h.precision}.",
        )
    return _dropped(path, "The quoted words do not contain this date, so it was dropped.")


def _cut(date: str, precision: str) -> str:
    at = datetime.fromisoformat(
        date.replace("Z", "+00:00") if "T" in date else date + "T00:00:00+00:00"
    )
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    at = at.astimezone(UTC)
    if precision == "year":
        return f"{at.year:04d}-01-01"
    if precision == "quarter":
        return f"{at.year:04d}-{(at.month - 1) // 3 * 3 + 1:02d}-01"
    if precision == "month":
        return f"{at.year:04d}-{at.month:02d}-01"
    if precision == "day":
        return f"{at:%Y-%m-%d}"
    if precision == "minute":
        return f"{at:%Y-%m-%dT%H:%M:00Z}"
    return f"{at:%Y-%m-%dT%H:%M:%SZ}"


def _covers_exact(h: DateHit, date: str, precision: str) -> bool:
    """The quoted date says ``date`` at least to ``precision``."""
    try:
        return _cut(h.date, precision) == _cut(date, precision)
    except ValueError:
        return False


def _verify_number(
    path: str, f: NumberField, checkable: bool, warnings: list[str], where: Any, note: Any
) -> Found:
    if f.value is None:
        return _dropped(path, "The file does not give this number.")
    ok, page = where(f)
    if not ok:
        warnings.append(f"{path}: {NOT_IN_FILE}")
        return _dropped(path, NOT_IN_FILE)
    if not checkable:
        return Found(
            path, f.value, "inferred", (f.evidence or "")[:EVIDENCE_MAX] or None, page, note(f)
        )
    stated = numbers_in(f.evidence or "")
    if _in_numbers(f.value, stated):
        return Found(path, f.value, f.confidence, (f.evidence or "")[:EVIDENCE_MAX], page, f.note)
    if path == "lifecycle.mass_kg":
        for n in stated:
            for factor, unit in ((1000.0, "tonnes"), (0.45359237, "pounds")):
                if abs(n * factor - f.value) <= abs(n * factor) * 0.005:
                    return Found(
                        path,
                        round(n * factor, 3),
                        "inferred",
                        (f.evidence or "")[:EVIDENCE_MAX],
                        page,
                        f"The file gives {n:g} {unit}; converted to kilograms.",
                    )
    return _dropped(path, "The quoted words do not contain this number, so it was dropped.")


def _prompt(doc: Doc, lex: Lexicon, filename: str, with_text: bool) -> str:
    lists = {
        "vehicles": {v.id: v.label for v in lex.vehicles},
        "pads": {p.id: p.label for p in lex.pads},
        "relays": {r.id: r.label for r in lex.relays},
        "sites": {s.id: s.name for s in lex.sites},
    }
    head = (
        f"File: {filename}\nCatalogue ids you may use:\n{json.dumps(lists, ensure_ascii=False)}\n"
    )
    if not with_text:
        return head + "\nThe document is attached. Fill in the form."
    unit = "page" if doc.paged else "line"
    body = "\n".join(f"[{unit} {n}] {t}" for n, t in doc.lines if t.strip())
    return (
        head
        + f"\nThe document, each {unit} numbered:\n{body[:MODEL_TEXT_MAX]}\n\nFill in the form."
    )


async def read_with_model(
    session: Session,
    doc: Doc,
    lex: Lexicon,
    *,
    filename: str,
    data: bytes,
    media_type: str,
    is_pdf: bool,
) -> tuple[Reading, str]:
    """The model's reading, checked against the file. Raises ``GeminiUnavailable`` when no
    model is configured, and ``ModelFailed`` when none gave a usable reading."""
    models = list(base.model_chain())
    light = base.model_chain(light=True)
    prompt = _prompt(doc, lex, filename, with_text=bool(doc.text.strip()))
    parts: list[dict[str, Any]] = []
    if is_pdf:
        parts.append({"inline_data": {"mime_type": "application/pdf", "data": data}})
    parts.append({"text": prompt})
    contents = [{"role": "user", "parts": parts}]
    schema = base._schema_for(ModelReading)
    t0 = time.perf_counter()
    tokens = [0, 0]
    tried: list[dict[str, Any]] = []
    status, model, error = "error", models[0] if models else "none", None
    result: Reading | None = None
    timed_out = False
    # The main chain first, then the light chain's models it does not already hold.
    chain = list(dict.fromkeys([*base._usable(models), *base._usable(list(light))]))
    deadline = time.monotonic() + MODEL_BUDGET_S
    try:
        for model in chain:
            left = deadline - time.monotonic()
            if left < MODEL_MIN_S:
                tried.append(
                    {"kind": "budget_spent", "model": model, "detail": f"{left:.0f} s left"}
                )
                break
            try:
                resp = await base._generate(
                    model,
                    contents,
                    SYSTEM,
                    [],
                    response_schema=schema,
                    timeout_s=min(MODEL_TIMEOUT_S, left),
                    max_output_tokens=MODEL_MAX_OUTPUT_TOKENS,
                )
            except base.ModelUnavailable as exc:
                base._cool(exc.model, exc.cooldown_s, exc.why)
                tried.append({"kind": "model_unavailable", "model": exc.model, "detail": exc.why})
                continue
            except TimeoutError:
                timed_out = True
                # Later requests skip it for a while instead of waiting on it again.
                base._cool(model, base.SLOW_MODEL_COOLDOWN_S, "did not answer in time")
                tried.append({"kind": "timeout", "model": model, "detail": "no answer in time"})
                continue
            tokens[0] += resp["prompt_tokens"]
            tokens[1] += resp["completion_tokens"]
            try:
                parsed = ModelReading.model_validate_json(resp["text"])
            except (ValidationError, ValueError) as exc:
                tried.append({"kind": "schema_invalid", "model": model, "detail": str(exc)[:300]})
                continue
            result = verify(parsed, doc, lex)
            status = "ok"
            return result, model
        if timed_out and not any(t["kind"] == "schema_invalid" for t in tried):
            status, error = "timeout", "The model did not answer in time."
        else:
            error = "No model could read the file right now."
        raise ModelFailed(error)
    except base.GeminiUnavailable:
        status, error = "degraded", "The model is not configured."
        raise
    except ModelFailed:
        raise
    except Exception as exc:
        log.exception("intake: the model reading failed")
        error = type(exc).__name__
        raise ModelFailed(error) from exc
    finally:
        await record_run(
            session,
            AgentRunRecord(
                agent="intake",
                model=model,
                status=status,
                request={"filename": filename, "media_type": media_type, "bytes": len(data)},
                response=None
                if result is None
                else {"fields": result.fields, "warnings": result.warnings},
                prompt_tokens=tokens[0],
                completion_tokens=tokens[1],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                attempts=1,
                guard_failures=tried or None,
                error=error if status == "error" else None,
                tool_calls=[],
            ),
        )
