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
#: exemption rather than a general tolerance.
SMALL_COUNTING_MAX = 12
YEAR_RANGE = (1900, 2200)

_NUMBER_RE = re.compile(
    r"""
    (?<![\w.])            # not mid-identifier
    (-?\d{1,3}(?:,\d{3})+(?:\.\d+)?   # 1,234.5
    |-?\d+\.\d+                        # 1.5
    |-?\d+)                            # 42
    (?![\w])
    """,
    re.VERBOSE,
)

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


def extract_claim_numbers(obj: Any) -> list[tuple[str, float, str]]:
    """Numbers asserted by an agent's output, from prose *and* structured fields.

    Walking the whole validated object, not just the free-text fields, is
    deliberate: a hallucinated value hidden in ``result.metrics.sunlit_h`` is
    exactly as damaging as one in a sentence, and is less likely to be noticed
    by a reader.
    """
    out: list[tuple[str, float, str]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, int | float):
            out.append((path, float(node), f"{path} = {node}"))
            return
        if isinstance(node, str):
            for m in _NUMBER_RE.finditer(node):
                raw = m.group(1).replace(",", "")
                try:
                    val = float(raw)
                except ValueError:
                    continue
                lo = max(0, m.start() - 45)
                hi = min(len(node), m.end() + 45)
                out.append((path, val, node[lo:hi].strip()))
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


def _is_exempt(value: float, claim: str) -> bool:
    """Numbers that are not claims about the data."""
    if value != int(value):
        return False
    iv = int(value)
    if YEAR_RANGE[0] <= iv <= YEAR_RANGE[1] and re.search(r"\b(19|20|21)\d{2}\b", claim):
        return True
    # Small integers are counts and ordinals ("one ridge", "three documents",
    # "the first site"). Anything the product actually reports is far larger:
    # hours are tens to hundreds, per cents are tens, seconds are thousands.
    return 0 <= iv <= SMALL_COUNTING_MAX


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


def check_grounding(output: dict[str, Any], tool_results: list[dict[str, Any]]) -> Verdict:
    """Every number in ``output`` must trace to ``tool_results``."""
    pool: list[tuple[str, float, str, int]] = []
    for call in tool_results:
        seq = int(call.get("seq", 0))
        tool = str(call.get("tool", "?"))
        result = call.get("result")
        for path, val in flatten_numbers(result):
            pool.append((tool, val, path, seq))
        if tool == USER_REQUEST_TOOL:
            # The user's request arrives as prose -- "600 hours of continuous
            # sunlight" -- so its numbers are inside strings and the numeric-leaf
            # walk above finds none. They are parsed out here and nowhere else:
            # doing the same for tool results would ground a claim against a
            # digit that happened to appear in a site name.
            for path, text in _string_leaves(result):
                for m in _NUMBER_RE.finditer(text):
                    try:
                        pool.append((tool, float(m.group(1).replace(",", "")), path, seq))
                    except ValueError:
                        continue

    claims = extract_claim_numbers(output)
    violations: list[Violation] = []
    citations: list[Citation] = []

    for _path, value, claim in claims:
        if _is_exempt(value, claim):
            continue
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
            nearby = sorted({round(v, 2) for _n, v, _f, _s in pool}, key=lambda x: abs(x - value))[
                :4
            ]
            violations.append(
                Violation(
                    kind="ungrounded_number",
                    detail=(
                        f"{value:g} does not appear in any tool result "
                        f"(in '{claim}'). Nearest available values: "
                        f"{', '.join(f'{n:g}' for n in nearby)}."
                    ),
                    value=value,
                )
            )
        else:
            tool, field_path, seq = hit
            citations.append(
                Citation(claim=claim, value=value, tool=tool, call_seq=seq, field=field_path)
            )

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


def check(output: dict[str, Any], tool_results: list[dict[str, Any]]) -> Verdict:
    """Run every guard. Grounding last, so structural problems report first."""
    violations: list[Violation] = []
    citations: list[Citation] = []
    for verdict in (
        check_refusal(output),
        check_negative_result(output),
        check_grounding(output, tool_results),
    ):
        violations.extend(verdict.violations)
        citations.extend(verdict.citations)
    return Verdict(ok=not violations, violations=violations, citations=citations)
