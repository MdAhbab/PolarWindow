"""Output guards. Pure functions over (validated output, tool results).

The central rule, and the one the brief calls the single most important guard:
**every numeric claim must trace to a tool call result.** A response containing
a number not present in the tool outputs is rejected and retried.

Why this is a pure function
---------------------------
``check(parsed, collected)`` takes two values and returns a verdict. No I/O, no
model, no session. That makes the highest-risk component in the system the
easiest one to test exhaustively, which is the right way round.

What counts as grounded, precisely
----------------------------------
A number in the output is grounded if some tool result contains a value it could
have come from, allowing for:

* **unit conversions we perform ourselves** -- seconds to hours, fraction to
  per cent. The tools speak seconds; humans read hours. Forbidding that would
  make the guard unusable and would push the model toward writing raw seconds,
  which is worse prose and no more truthful.
* **rounding to a stated precision** -- 0.7983 may be written as "80 %". The
  comparison is against the tool value rounded the same way, not against an
  arbitrary tolerance.

And it is *not* grounded merely because it is arithmetically correct. If the
tools returned 204,120 s and 708.7 h, and the model writes "288 hours of
sunlight", that division is right -- and it is still rejected, because the guard
cannot distinguish correct arithmetic from lucky arithmetic, and a model that
is allowed to derive is a model that is allowed to derive wrongly. Derivations
belong in tools.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

#: Numbers that are never factual claims about the data.
#:
#: Without this the guard is uselessly strict: "the first site", "one ridge",
#: "2027" and "three documents" would all be violations, and the model would be
#: forced into stilted prose to avoid them. Each entry is a specific, bounded
#: exemption rather than a general tolerance -- and a small number stops being
#: exempt the moment it carries a unit (see ``_QUANTITY_AFTER``), because
#: "9 %" and "10 h" are measurements, not counts.
SMALL_COUNTING_MAX = 12
YEAR_RANGE = (1900, 2200)

#: A number as written. Deliberately permissive about what *follows* it: an
#: earlier version required a non-word character after the digits, so "999h",
#: "873km" and "7e5" were not seen as numbers at all and passed the guard
#: unchecked. The lookbehind still refuses digits glued to a word on their left
#: ("de440", "LDEM_80S"), which are identifiers, not claims.
_NUMBER_RE = re.compile(
    r"""
    (?<![\w.])                                   # not mid-identifier
    (?P<num>
        [-\u2212]?\d{1,3}(?:,\d{3})+(?:\.\d+)?     # 1,234.5
      | [-\u2212]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?    # 42, 1.5, 7e5
      | [-\u2212]?\.\d+                           # .95
    )
    """,
    re.VERBOSE,
)

#: Units and quantity words that make a small integer a measurement.
_QUANTITY_AFTER = re.compile(
    r"""^\s*(?:
        %|per\s?cent|percent
      | h\b|hrs?\b|hours?\b|-hours?\b|-h\b
      | d\b|days?\b|-days?\b
      | min\b|minutes?\b|s\b|secs?\b|seconds?\b
      | km\b|m\b|metres?\b|meters?\b|-metre\b|-meter\b
      | °|deg\b|degrees?\b|-degree\b
      | w\b|watts?\b|k\b|kelvin\b
    )""",
    re.VERBOSE | re.IGNORECASE,
)

#: Calendar dates are positions in time, not claims about a site. ISO stamps
#: are removed before scanning; a day-of-month beside a month name is exempt.
_ISO_DATETIME = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?)?\b")
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_DAY_MONTH = re.compile(rf"^\s*(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{_MONTHS})\b", re.IGNORECASE)
_MONTH_DAY = re.compile(rf"\b(?:{_MONTHS})\.?\s+$", re.IGNORECASE)

#: Cardinal number words. Values up to twelve are counts in prose ("three
#: documents") and are exempt exactly as the digits would be; anything larger
#: written out in words -- "three hundred hours" -- is a claim and is checked.
_UNITS_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS_WORDS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_SCALE_WORDS = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}
_WORD_NUMBER_RE = re.compile(
    r"\b(?:" + "|".join([*_UNITS_WORDS, *_TENS_WORDS, *_SCALE_WORDS]) + r")"
    r"(?:(?:[\s-]+|\s+and\s+)(?:"
    + "|".join([*_UNITS_WORDS, *_TENS_WORDS, *_SCALE_WORDS])
    + r"))*\b",
    re.IGNORECASE,
)


def _parse_number_words(phrase: str) -> float | None:
    """'three hundred and twenty-two' -> 322. None when it is not one number."""
    total = current = 0
    seen = False
    for word in re.split(r"[\s-]+", phrase.lower()):
        if word == "and" or not word:
            continue
        if word in _UNITS_WORDS:
            current += _UNITS_WORDS[word]
        elif word in _TENS_WORDS:
            current += _TENS_WORDS[word]
        elif word == "hundred":
            current = (current or 1) * 100
        elif word in ("thousand", "million"):
            total += (current or 1) * _SCALE_WORDS[word]
            current = 0
        else:
            return None
        seen = True
    return float(total + current) if seen else None


#: Per-cent and hour conversions the guard performs on tool values before
#: comparing. Order matters only for reporting.
_DERIVED_SCALES: tuple[tuple[str, float], ...] = (
    ("identity", 1.0),
    ("seconds->hours", 1.0 / 3600.0),
    ("seconds->days", 1.0 / 86400.0),
    ("fraction->percent", 100.0),
    ("degrees->arcminutes", 60.0),
)


@dataclass(frozen=True, slots=True)
class Violation:
    kind: str
    detail: str
    value: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "value": self.value}


@dataclass(frozen=True, slots=True)
class Citation:
    claim: str
    value: float
    tool: str
    call_seq: int
    field: str


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    violations: list[Violation] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)

    def repair_hint(self) -> str:
        """The message sent back to the model on the one retry it gets.

        Naming the offending numbers specifically is what makes the retry work:
        "your output contained an ungrounded number" produces another guess,
        while "72 is not in the tool results; the tool returned 70 and 80"
        produces a correction.
        """
        lines = ["Your previous answer was rejected. Fix these and answer again:"]
        for v in self.violations:
            lines.append(f"  - {v.detail}")
        lines.append(
            "Use ONLY numbers that appear in the tool results. Do not calculate new "
            "numbers from them. If a number you need is not available, say so using "
            "status='insufficient_data' instead of estimating."
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Flattening
# ---------------------------------------------------------------------------


def flatten_numbers(obj: Any, prefix: str = "") -> list[tuple[str, float]]:
    """Every numeric leaf of a JSON-like structure, with its path.

    Booleans are excluded: ``True`` is an ``int`` in Python and would otherwise
    ground every "1" in the output.
    """
    out: list[tuple[str, float]] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, int | float):
        if math.isfinite(float(obj)):
            out.append((prefix or "value", float(obj)))
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(flatten_numbers(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    if isinstance(obj, list | tuple):
        for i, v in enumerate(obj):
            out.extend(flatten_numbers(v, f"{prefix}[{i}]"))
        return out
    return out


#: The pseudo-tool under which the user's own request enters the pool.
USER_REQUEST_TOOL = "user_request"


def _string_leaves(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Every string leaf of a JSON-like structure, with its path."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, str):
        out.append((prefix or "value", obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_string_leaves(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list | tuple):
        for i, v in enumerate(obj):
            out.extend(_string_leaves(v, f"{prefix}[{i}]"))
    return out


@dataclass(frozen=True, slots=True)
class Claim:
    """One number the output asserts, and where."""

    path: str
    value: float
    context: str
    #: True for a number written in prose (a string leaf), False for a value
    #: in a structured field. Only prose may quote the user's own request.
    in_prose: bool
    #: The number is a bare count: a small integer carrying no unit.
    bare_count: bool = False
    #: The number is a calendar position (a day of the month, a year).
    is_date: bool = False


def _scan_text(text: str, path: str) -> list[Claim]:
    out: list[Claim] = []
    cleaned = _ISO_DATETIME.sub(lambda m: " " * len(m.group(0)), text)
    for m in _NUMBER_RE.finditer(cleaned):
        raw = m.group("num").replace(",", "").replace("\u2212", "-")
        try:
            val = float(raw)
        except ValueError:
            continue
        after = cleaned[m.end() : m.end() + 16]
        before = cleaned[max(0, m.start() - 12) : m.start()]
        is_int = val == int(val) and "." not in raw and "e" not in raw.lower()
        is_date = (
            is_int and 1 <= val <= 31 and bool(_DAY_MONTH.match(after) or _MONTH_DAY.search(before))
        )
        lo, hi = max(0, m.start() - 45), min(len(text), m.end() + 45)
        out.append(
            Claim(
                path=path,
                value=val,
                context=text[lo:hi].strip(),
                in_prose=True,
                bare_count=is_int and not _QUANTITY_AFTER.match(after),
                is_date=is_date,
            )
        )
    for m in _WORD_NUMBER_RE.finditer(cleaned):
        worded = _parse_number_words(m.group(0))
        if worded is None:
            continue
        after = cleaned[m.end() : m.end() + 16]
        lo, hi = max(0, m.start() - 45), min(len(text), m.end() + 45)
        out.append(
            Claim(
                path=path,
                value=worded,
                context=text[lo:hi].strip(),
                in_prose=True,
                bare_count=not _QUANTITY_AFTER.match(after),
            )
        )
    return out


def extract_claims(obj: Any) -> list[Claim]:
    """Numbers asserted by an agent's output, from prose *and* structured fields.

    Walking the whole validated object, not just the free-text fields, is
    deliberate: a hallucinated value hidden in ``result.metrics.sunlit_h`` is
    exactly as damaging as one in a sentence, and is less likely to be noticed
    by a reader.
    """
    out: list[Claim] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, int | float):
            out.append(
                Claim(path=path, value=float(node), context=f"{path} = {node}", in_prose=False)
            )
            return
        if isinstance(node, str):
            out.extend(_scan_text(node, path))
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
            return
        if isinstance(node, list | tuple):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(obj, "")
    return out


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def _is_exempt(claim: Claim) -> bool:
    """Numbers that are not claims about the data.

    A small integer is a count ("three documents", "the first site") only when
    it carries no unit: the old rule exempted every integer up to twelve, so
    "Earth is visible 9 % of the time" and "a 10 h blackout" were never checked.
    Structured numeric fields are never exempt as counts -- a value in
    ``observed_value`` is a measurement whatever its size.
    """
    value = claim.value
    if claim.is_date:
        return True
    if value != int(value):
        return False
    iv = int(value)
    if (
        claim.in_prose
        and YEAR_RANGE[0] <= iv <= YEAR_RANGE[1]
        and re.search(r"\b(19|20|21)\d{2}\b", claim.context)
    ):
        return True
    if claim.in_prose:
        return claim.bare_count and 0 <= iv <= SMALL_COUNTING_MAX
    # Ranks and counts in structured fields ("rank": 1) are small by nature and
    # sit in fields whose meaning is a position, not a measurement.
    return claim.path.rsplit(".", 1)[-1] in _STRUCTURED_COUNT_FIELDS and 0 <= iv <= 50


#: Structured fields whose integers are positions or counts, not measurements.
_STRUCTURED_COUNT_FIELDS = frozenset({"rank", "position", "count", "call_seq", "seq"})


def _match(value: float, pool: list[tuple[str, float, str, int]]) -> tuple[str, str, int] | None:
    """Find a tool value this claim could have come from.

    Matching is done at the claim's own written precision. A claim of "80" is
    satisfied by a tool value of 0.7983 (as a percentage: 79.83, which rounds to
    80) but not by 0.75. A claim of "79.8" needs the tool value to agree to that
    decimal place. This ties the strictness of the check to how precise the
    model chose to be, which is the right coupling: claiming more precision
    should be harder to justify, not easier.
    """
    decimals = 0
    s = f"{value:.10f}".rstrip("0")
    if "." in s:
        decimals = len(s.split(".")[1])
    decimals = min(decimals, 3)

    for name, tool_value, field_path, seq in pool:
        for _label, scale in _DERIVED_SCALES:
            converted = tool_value * scale
            if not math.isfinite(converted):
                continue
            if round(converted, decimals) == round(value, decimals):
                return name, field_path, seq
            # Also allow the claim to be the rounded form at lower precision,
            # which covers "about 80 %" against 79.83.
            if decimals == 0 and abs(converted - value) < 0.5:
                return name, field_path, seq
    return None


_MONTH_NUMBER = {
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
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")
_MONTH_D_YEAR = re.compile(rf"\b({_MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
_D_MONTH_YEAR = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTHS})\.?,?\s+(\d{{4}})\b", re.I
)


def calendar_dates(text: str) -> list[tuple[str, str]]:
    """Every full calendar date in ``text``, as ``(YYYY-MM-DD, context)``.

    Three spellings: ISO (``2025-03-06``, with or without a time), "March 6,
    2025" and "6 March 2025". A month or a year on its own is not a date claim
    and is not returned.
    """
    out: list[tuple[str, str]] = []

    def ctx(m: re.Match[str]) -> str:
        return text[max(0, m.start() - 40) : m.end() + 40].strip()

    for m in _ISO_DATE.finditer(text):
        out.append((f"{m.group(1)}-{m.group(2)}-{m.group(3)}", ctx(m)))
    for m in _MONTH_D_YEAR.finditer(text):
        month = _MONTH_NUMBER.get(m.group(1).lower())
        if month:
            out.append((f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}", ctx(m)))
    for m in _D_MONTH_YEAR.finditer(text):
        month = _MONTH_NUMBER.get(m.group(2).lower())
        if month:
            out.append((f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}", ctx(m)))
    return out


def check_dates(output: dict[str, Any], tool_results: list[dict[str, Any]]) -> list[Violation]:
    """A full calendar date in an answer must appear in a tool result or the request.

    Dates used to be exempt as "positions in time", which was safe while every
    date an agent saw was a window edge. Mission launches and landings are
    facts, and "IM-4 lands on 2027-05-01" is exactly the invention this guard
    exists to catch.
    """
    known: set[str] = set()
    for call in tool_results:
        for _path, text in _string_leaves(call.get("result")):
            known.update(d for d, _c in calendar_dates(text))
    violations: list[Violation] = []
    for _path, text in _string_leaves(output):
        for day, context in calendar_dates(text):
            if day not in known:
                violations.append(
                    Violation(
                        kind="ungrounded_date",
                        detail=(
                            f"The date {day} (in '{context}') does not appear in any tool "
                            f"result. Use only dates the tools returned."
                        ),
                        value=None,
                    )
                )
    return violations


def check_grounding(output: dict[str, Any], tool_results: list[dict[str, Any]]) -> Verdict:
    """Every number in ``output`` must trace to ``tool_results``.

    Two pools, not one. Tool results ground anything. The user's own request
    grounds only *prose* -- "no site gives you the 600 hours you asked for" is
    quoting -- and never a structured field: an ``observed_value`` equal to the
    user's threshold is exactly the hallucination the guard exists to stop, and
    with a single pool it was grounded against the requirement it was supposed
    to be measured against.
    """
    measured: list[tuple[str, float, str, int]] = []
    quoted: list[tuple[str, float, str, int]] = []
    for call in tool_results:
        seq = int(call.get("seq", 0))
        tool = str(call.get("tool", "?"))
        result = call.get("result")
        if tool == USER_REQUEST_TOOL:
            # The user's request arrives as prose -- "600 hours of continuous
            # sunlight" -- so its numbers are inside strings. They are parsed out
            # here and nowhere else: doing the same for tool results would ground
            # a claim against a digit that happened to appear in a site name.
            for path, val in flatten_numbers(result):
                quoted.append((tool, val, path, seq))
            for path, text in _string_leaves(result):
                for c in _scan_text(text, path):
                    quoted.append((tool, c.value, path, seq))
            continue
        for path, val in flatten_numbers(result):
            measured.append((tool, val, path, seq))

    violations: list[Violation] = []
    citations: list[Citation] = []

    for claim in extract_claims(output):
        if _is_exempt(claim):
            continue
        pool = measured + quoted if claim.in_prose else measured
        value = claim.value
        if not pool:
            violations.append(
                Violation(
                    kind="ungrounded_no_tools",
                    detail=(
                        f"The answer contains the number {value:g} but no tool was "
                        f"called, so there is nothing it could have come from."
                    ),
                    value=value,
                )
            )
            continue
        hit = _match(value, pool)
        if hit is None:
            nearby = sorted(
                {round(v, 2) for _n, v, _f, _s in measured}, key=lambda x: abs(x - value)
            )[:4]
            where = "" if claim.in_prose else f" (structured field `{claim.path}`)"
            violations.append(
                Violation(
                    kind="ungrounded_number",
                    detail=(
                        f"{value:g} does not appear in any tool result{where} "
                        f"(in '{claim.context}'). Nearest measured values: "
                        f"{', '.join(f'{n:g}' for n in nearby) or 'none'}."
                    ),
                    value=value,
                )
            )
        else:
            tool, field_path, seq = hit
            citations.append(
                Citation(
                    claim=claim.context, value=value, tool=tool, call_seq=seq, field=field_path
                )
            )

    violations.extend(check_dates(output, tool_results))
    return Verdict(ok=not violations, violations=violations, citations=citations)


def check_refusal(output: dict[str, Any]) -> Verdict:
    """``insufficient_data`` must carry a reason; ``ok`` must carry content.

    Both directions matter. A refusal without a reason is a shrug, and an "ok"
    with empty fields is a silent failure that renders as a blank card.
    """
    status = output.get("status")
    if status == "insufficient_data":
        if not (output.get("reason") or "").strip():
            return Verdict(
                ok=False,
                violations=[
                    Violation(
                        kind="refusal_without_reason",
                        detail="status is 'insufficient_data' but no reason was given. "
                        "Say what is missing.",
                    )
                ],
            )
        return Verdict(ok=True)

    if status == "ok":
        # "Nothing qualifies" is a complete answer, not an empty one -- and it
        # is the specific case the advisor exists to get right, so an empty
        # `ranked` list must not be mistaken for a failure to answer.
        content_fields = (
            "paragraph",
            "ranked",
            "answer",
            "nothing_satisfies_message",
            "planner_memo",
            "lesson_plan",
            "public_explainer",
        )
        if not any(output.get(f) for f in content_fields):
            return Verdict(
                ok=False,
                violations=[
                    Violation(
                        kind="empty_ok",
                        detail="status is 'ok' but every content field is empty. Either "
                        "answer, or return status='insufficient_data' with a reason.",
                    )
                ],
            )
    return Verdict(ok=True)


def check_negative_result(output: dict[str, Any]) -> Verdict:
    """A2 must say plainly when nothing satisfies the requirement.

    The failure mode is specific and worth guarding individually: a helpful
    model presented with sites that all miss the requirement will rank the
    least-bad one and describe it warmly, and a reader will take that as a pass.
    """
    if "any_satisfies" not in output:
        return Verdict(ok=True)
    if (
        output.get("any_satisfies") is False
        and not (output.get("nothing_satisfies_message") or "").strip()
    ):
        return Verdict(
            ok=False,
            violations=[
                Violation(
                    kind="missing_negative_statement",
                    detail="No site satisfies the requirement, but the answer does not "
                    "say so. State plainly that nothing meets it before ranking "
                    "anything.",
                )
            ],
        )
    return Verdict(ok=True)


#: Words that judge the whole instead of showing the evidence (docs/conventions.md,
#: invariant 9): a go/no-go, "safe", a readiness percentage, a risk score, an overall
#: chance of launch. Each pattern names one of those; plain uses of "ready" or "risk"
#: (a readiness item, a risk on the list) are not in it.
VERDICT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bgo\s*/\s*no[- ]?go\b",
        r"\bno[- ]go\b",
        r"\b(?:is|are|it's|looks like) a go\b",
        r"\bgo for (?:launch|landing|flight)\b",
        r"\b(?:un)?safe(?:ly)?\b",
        r"\breadiness (?:percentage|score|index|level of \d)",
        r"\b\d+(?:\.\d+)?\s?(?:%|per ?cent) (?:ready|complete|go)\b",
        r"\bready to (?:launch|fly|land)\b",
        r"\bcleared (?:for|to) (?:launch|fly|land)\b",
        r"\brisk (?:score|rating|index)\b",
        r"\blikelihood\s*(?:times|x|×|\*)\s*consequence\b",
        r"\b(?:overall|total|combined) (?:chance|probability|likelihood|odds) "
        r"(?:of|that|for) (?:a |the )?(?:launch|launching|success|going|landing)",
        r"\b(?:recommend|advise)\w* (?:launching|to launch|scrubbing|to scrub|a scrub)\b",
    )
)

#: Fields that echo the user's own words back; a verdict word there is theirs.
_ECHO_FIELDS = frozenset({"question", "interpreted_as", "requirement_summary"})


def check_verdict_words(output: dict[str, Any]) -> Verdict:
    """No verdicts (invariant 9): the answer shows the evidence rule by rule and people
    decide. A verdict word is rejected even in a denial ("it is not safe" judges too)."""
    violations = []
    for path, text in _string_leaves(output):
        if path.split(".")[0].split("[")[0] in _ECHO_FIELDS:
            continue
        for pat in VERDICT_PATTERNS:
            m = pat.search(text)
            if m:
                violations.append(
                    Violation(
                        kind="verdict_word",
                        detail=f"'{m.group(0)}' in {path} is a verdict. Do not judge the "
                        "whole, not even to deny it: say what each number or rule shows "
                        "and leave the decision to the people reading it.",
                    )
                )
                break
    return Verdict(ok=not violations, violations=violations)


def check(output: dict[str, Any], tool_results: list[dict[str, Any]]) -> Verdict:
    """Run every guard. Grounding last, so structural problems report first."""
    violations: list[Violation] = []
    citations: list[Citation] = []
    for verdict in (
        check_refusal(output),
        check_negative_result(output),
        check_verdict_words(output),
        check_grounding(output, tool_results),
    ):
        violations.extend(verdict.violations)
        citations.extend(verdict.citations)
    return Verdict(ok=not violations, violations=violations, citations=citations)
