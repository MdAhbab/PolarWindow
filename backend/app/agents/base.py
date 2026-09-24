"""One bounded function-calling loop, shared by all four agents.

ADR-3 chose this over a graph for one reason: there is no branching to model.
Every agent is gather -> generate -> validate -> (repair once) -> done. The only
cycle is the guard retry, which is a ``for attempt in (1, 2)``.

The property that matters most is that **there is no code path from a model
response to an HTTP response that skips ``guards.check``**. A graph would express
that as an edge, which is configuration; here it is a function call in a
straight line.

Every exit writes an ``agent_runs`` row -- success, guard rejection, timeout,
outage. That completeness is the point: the table is shown in the demo as
evidence the layer is real and bounded, and a missing row for a failure would
quietly make it evidence of something else.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from app.agents import guards, tools
from app.agents.tools import Session
from app.config import get_settings
from app.services.agent_log import AgentRunRecord, ToolCallRecord, record_run

log = logging.getLogger(__name__)


class AgentStatus:
    """The six terminal states, recorded verbatim in ``agent_runs.status``.

    The HTTP envelope folds the last four into ``degraded`` -- to a reader they
    are the same thing, a measurement-only answer -- but the run log keeps them
    apart, because "the guard rejected it twice", "the model timed out" and
    "the code failed" are different findings and the log is the evidence for
    which one happened.
    """

    OK = "ok"
    INSUFFICIENT = "insufficient_data"
    GUARD_REJECTED = "guard_rejected"
    TIMEOUT = "timeout"
    DEGRADED = "degraded"  # the model is not configured or not reachable
    ERROR = "error"


BUDGET_SPENT_PROMPT = (
    "Tool call budget exhausted. Answer with what you have, or "
    "return status='insufficient_data'."
)
ANSWER_NOW_PROMPT = "Now answer. Respond ONLY with JSON matching the required schema."


class DeadlineExceeded(TimeoutError):
    """The agent's whole wall-clock budget is spent."""


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Everything that distinguishes one agent from another.

    Four fields. If a fifth is ever needed, that is the signal ADR-3 said to
    watch for -- the loop has stopped fitting and the graph should be revisited.
    """

    name: str
    system_prompt: str
    tool_names: tuple[str, ...]
    output_model: type[BaseModel]
    #: The model chain to try, in order; the settings' chain when None.
    models: tuple[str, ...] | None = None
    max_rounds: int | None = None


@dataclass
class AgentOutcome:
    status: str
    result: dict[str, Any] | None
    reason: str | None
    provenance: list[dict[str, Any]] = field(default_factory=list)
    run_id: str | None = None
    tool_calls: list[tools.ToolCallLog] = field(default_factory=list)
    attempts: int = 1
    latency_ms: float = 0.0
    guard_failures: list[dict[str, Any]] = field(default_factory=list)
    #: The model that answered, or the last one tried.
    model: str | None = None


# ---------------------------------------------------------------------------
# Model transport
# ---------------------------------------------------------------------------


class GeminiUnavailable(RuntimeError):
    pass


class ModelUnavailable(RuntimeError):
    """This model cannot answer now, and the next model in the chain might.

    Raised for a quota that is used up (429), a model this key cannot use or
    that is not served under that name (403, 404), and an outage (5xx). Not for
    a malformed request: the next model would reject it too.
    """

    def __init__(self, model: str, why: str, cooldown_s: float) -> None:
        super().__init__(f"{model}: {why}")
        self.model = model
        self.why = why
        self.cooldown_s = cooldown_s


#: When each model may be tried again, in `time.monotonic()` seconds. Kept in
#: the process: after a restart the first request finds out again, once.
_cooldown_until: dict[str, float] = {}
#: Why each model is being skipped, for the settings screen.
_cooldown_why: dict[str, str] = {}


def _cool(model: str, seconds: float, why: str = "") -> None:
    _cooldown_until[model] = max(_cooldown_until.get(model, 0.0), time.monotonic() + seconds)
    if why:
        _cooldown_why[model] = why


def model_states(models: tuple[str, ...]) -> list[dict[str, Any]]:
    """Each model in a chain: ready, or skipped until when and why."""
    now_mono = time.monotonic()
    now = datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for m in models:
        left = _cooldown_until.get(m, 0.0) - now_mono
        out.append(
            {
                "model": m,
                "ready": left <= 0,
                "skipped_until": now + timedelta(seconds=left) if left > 0 else None,
                "why": _cooldown_why.get(m) if left > 0 else None,
            }
        )
    return out


@dataclass(frozen=True, slots=True)
class AgentRuntime:
    """What the project manager's settings change without a restart.

    Set per request by the route, from the stored settings, so every process
    serving the API follows the same switch.
    """

    enabled: bool = True
    #: The model chains in the order the settings give; None means the defaults.
    models: tuple[str, ...] | None = None
    models_light: tuple[str, ...] | None = None


_DEFAULT_RUNTIME = AgentRuntime()
_runtime: ContextVar[AgentRuntime | None] = ContextVar("agent_runtime", default=None)


def _current() -> AgentRuntime:
    return _runtime.get() or _DEFAULT_RUNTIME


@contextmanager
def agent_runtime(rt: AgentRuntime) -> Iterator[None]:
    token = _runtime.set(rt)
    try:
        yield
    finally:
        _runtime.reset(token)


def model_chain(light: bool = False) -> tuple[str, ...]:
    """The chain to try: the settings' order when one is stored, else the defaults."""
    s = get_settings()
    rt = _current()
    if light:
        return rt.models_light or s.agent_models_light
    return rt.models or s.agent_models


def _usable(models: list[str]) -> list[str]:
    now = time.monotonic()
    return [m for m in models if _cooldown_until.get(m, 0.0) <= now]


def reset_model_cooldowns() -> None:
    """Forget every cooldown: for tests, after a key's quota is raised, and from Settings."""
    _cooldown_until.clear()
    _cooldown_why.clear()


def _seconds_to_daily_reset(now: datetime | None = None) -> float:
    """Seconds until the Gemini API's daily quotas reset: midnight Pacific time."""
    tz = ZoneInfo("America/Los_Angeles")
    local = (now or datetime.now(UTC)).astimezone(tz)
    midnight = datetime.combine(local.date() + timedelta(days=1), dt_time(0, 0), tzinfo=tz)
    return max(60.0, (midnight - local).total_seconds())


_RETRY_DELAY = re.compile(r"retryDelay\W+(\d+(?:\.\d+)?)s")


def classify_api_error(model: str, code: object, details: str) -> ModelUnavailable | None:
    """Whether an API error means "try the next model", and for how long to skip this one."""
    if code == 429:
        if "PerDay" in details or "per day" in details.lower():
            return ModelUnavailable(model, "daily quota used up", _seconds_to_daily_reset())
        m = _RETRY_DELAY.search(details)
        return ModelUnavailable(
            model, "per-minute quota used up", float(m.group(1)) + 1.0 if m else 60.0
        )
    if code == 403:
        return ModelUnavailable(model, "not available to this API key", 6 * 3600.0)
    if code == 404:
        return ModelUnavailable(model, "not served under this name", 6 * 3600.0)
    if isinstance(code, int) and 500 <= code < 600:
        return ModelUnavailable(model, f"the service answered {code}", 30.0)
    return None


async def _generate(
    model: str,
    contents: list[Any],
    system_prompt: str,
    tool_decls: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any] | None,
    timeout_s: float,
) -> dict[str, Any]:
    """One call to Gemini via google-genai's async client.

    Isolated behind a function so the whole loop can be exercised offline. The
    SDK's async client speaks httpx, so tests can intercept it at the HTTP layer
    with respx; the autouse fixture in conftest additionally blanks the key, so
    a test that forgets its mock fails loudly instead of reaching the network.

    Returns the model's own ``Content`` alongside the parsed calls. Gemini 3
    models sign their reasoning and attach the signature to function-call parts;
    the next turn must send that content back unchanged or the call is rejected.
    Rebuilding a function-call part from its name and arguments drops the
    signature, so the loop appends ``model_content`` verbatim instead.
    """
    s = get_settings()
    if s.offline:
        raise GeminiUnavailable("OFFLINE=1: the model is not called; answering from measurements")
    if not s.gemini_api_key:
        raise GeminiUnavailable("PW_GEMINI_API_KEY is not set")

    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as gt

    client = genai.Client(api_key=s.gemini_api_key)
    config: dict[str, Any] = {
        "system_instruction": system_prompt,
        "max_output_tokens": s.agent_max_output_tokens,
        # The loop in run_agent executes tools itself, bounded and logged; the
        # SDK must never call anything on its own.
        "automatic_function_calling": gt.AutomaticFunctionCallingConfig(disable=True),
    }
    # Gemini 3 models are tuned for their default temperature; lowering it is
    # documented to cause looping in agentic use. Only set it when configured.
    if s.agent_temperature is not None:
        config["temperature"] = s.agent_temperature
    if tool_decls:
        config["tools"] = [gt.Tool(function_declarations=tool_decls)]
    if response_schema is not None:
        config["response_mime_type"] = "application/json"
        config["response_schema"] = response_schema

    try:
        resp = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model, contents=contents, config=gt.GenerateContentConfig(**config)
            ),
            timeout=timeout_s,
        )
    except genai_errors.APIError as exc:
        unavailable = classify_api_error(model, exc.code, f"{exc.status} {exc.details}")
        if unavailable is None:
            raise
        raise unavailable from exc

    calls: list[dict[str, Any]] = []
    text_parts: list[str] = []
    model_content: Any = None
    for i, cand in enumerate(getattr(resp, "candidates", None) or []):
        content = getattr(cand, "content", None)
        if i == 0:
            model_content = content
        for part in getattr(content, "parts", None) or []:
            fc = getattr(part, "function_call", None)
            if fc is not None:
                calls.append({"name": fc.name, "args": dict(fc.args or {})})
            # Thought parts carry the model's reasoning summary, not its answer.
            if getattr(part, "thought", False):
                continue
            txt = getattr(part, "text", None)
            if txt:
                text_parts.append(txt)

    usage = getattr(resp, "usage_metadata", None)
    return {
        "function_calls": calls,
        "text": "".join(text_parts),
        "model_content": model_content,
        "prompt_tokens": int(getattr(usage, "prompt_token_count", 0) or 0),
        "completion_tokens": int(getattr(usage, "candidates_token_count", 0) or 0),
    }


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def _hours(seconds: object) -> float | None:
    return float(seconds) / 3600.0 if isinstance(seconds, int | float) else None


def _fmt_h(seconds: object, *, open_: object = False) -> str | None:
    h = _hours(seconds)
    if h is None:
        return None
    return f"{'at least ' if open_ else 'about '}{h:.0f} hours"


def _metric_sentences(r: dict[str, Any], name: str) -> list[str]:
    """Plain sentences for one site's four numbers, skipping anything absent.

    Absent is never printed as zero: an earlier fallback wrote "0 hours" for a
    missing field, which is a measurement nobody made.
    """
    out: list[str] = []
    sun = _fmt_h(r.get("sunlit_s"))
    earth = _fmt_h(r.get("earth_contact_s"))
    frac_s, frac_e = r.get("sun_fraction_up"), r.get("earth_fraction_up")
    if sun is not None:
        pct = f" ({frac_s * 100:.0f}% of the window)" if isinstance(frac_s, float) else ""
        out.append(f"Over the requested window {name} is sunlit for {sun}{pct}.")
    if earth is not None:
        pct = f" ({frac_e * 100:.0f}%)" if isinstance(frac_e, float) else ""
        out.append(f"Earth is above its skyline for {earth}{pct}.")
    dark = _fmt_h(r.get("longest_dark_s"), open_=r.get("longest_dark_open"))
    if dark is not None:
        cut = (
            " -- the window ends it, so the night itself is longer"
            if r.get("longest_dark_open")
            else ""
        )
        out.append(f"The longest unbroken darkness is {dark}{cut}.")
    blackout = _fmt_h(r.get("longest_blackout_s"), open_=r.get("longest_blackout_open"))
    if blackout is not None:
        out.append(f"The longest unbroken loss of Earth contact is {blackout}.")
    u = r.get("uncertainty")
    if isinstance(u, dict):
        if u.get("grazing"):
            out.append(
                "At least one crossing is too shallow to time, so its edges are not "
                "knowable from this data; the totals stand."
            )
        elif u.get("terrain_modelled") is False:
            # A smooth-sphere skyline has no height error, so its margin is not
            # zero hours: there is no stated margin at all.
            out.append(
                "Terrain is not modelled here, so the skyline is a smooth Moon: the arc "
                "edges carry no stated margin, and real hills could only block more."
            )
        elif isinstance(u.get("edge_timing_s"), int | float):
            edge_h = u["edge_timing_s"] / 3600
            out.append(
                (
                    f"Arc edges are uncertain by up to {edge_h:.0f} hours "
                    if edge_h >= 1
                    else "Arc edges are uncertain by less than an hour "
                )
                + "from the elevation model's vertical error."
            )
    return out


def _facts(tool_calls: list[tools.ToolCallLog]) -> tuple[list[str], str | None]:
    """Sentences built only from tool results, and the site they are about."""
    facts: list[str] = []
    site_id: str | None = None
    names: dict[str, str] = {}
    for call in tool_calls:
        r = call.result or {}
        if call.error:
            continue
        if call.tool == "get_site":
            site_id = site_id or r.get("site_id")
            name = str(r.get("name") or r.get("site_id") or "the site")
            names[str(r.get("site_id"))] = name
            lat, lon, elev = r.get("lat_deg"), r.get("lon_deg"), r.get("elev_m")
            if all(isinstance(v, int | float) for v in (lat, lon, elev)):
                facts.append(
                    f"{name} sits at {lat:.3f} degrees latitude, {lon:.3f} degrees east, "
                    f"at an elevation of {elev:.0f} m."
                )
        elif call.tool == "get_metrics":
            site_id = site_id or r.get("site_id")
            facts.extend(_metric_sentences(r, names.get(str(r.get("site_id")), "this site")))
        elif call.tool == "get_horizon_profile":
            top, bearing = r.get("max_el_deg"), r.get("max_el_bearing_deg")
            if isinstance(top, int | float) and isinstance(bearing, int | float):
                facts.append(
                    f"Its highest skyline is {top:.2f} degrees at a bearing of "
                    f"{bearing:.0f} degrees."
                )
        elif call.tool == "compare_sites":
            for item in r.get("items") or []:
                if isinstance(item, dict):
                    facts.extend(_metric_sentences(item, str(item.get("site_id"))))
        elif call.tool == "search_sites":
            found = [row.get("name") for row in r.get("sites") or [] if isinstance(row, dict)]
            if found:
                facts.append("The search found: " + ", ".join(str(x) for x in found) + ".")
    return facts, site_id


def deterministic_summary(
    spec: AgentSpec,
    tool_calls: list[tools.ToolCallLog],
    reason: str,
    request_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A correct answer built from tool results alone, with no model involved.

    This is what makes the degrade path real rather than aspirational. If the
    model is unreachable, or if it fails the guard twice, the user still gets
    the four numbers -- assembled from values that are grounded by
    construction, labelled ``degraded`` so nobody mistakes it for the written
    answer, and shaped as *this agent's* contract, so a client reading an
    advisor response never receives an explainer's fields.

    The advisor is the exception that proves the rule: evaluating a
    requirement written in prose needs the model, so its fallback states the
    measurements and says plainly that the requirement was not assessed --
    rather than guessing which sites pass.
    """
    facts, site_id = _facts(tool_calls)
    paragraph = " ".join(facts)
    status = "ok" if facts else "insufficient_data"
    req = request_payload or {}
    name = spec.output_model.__name__

    if name == "TradeOffAdvice":
        not_assessed = (
            "The requirement was not assessed: that needs the written answer, which is "
            "unavailable. No site is claimed to meet it."
        )
        payload: dict[str, Any] = {
            "status": "insufficient_data",
            "reason": f"{reason} {not_assessed} {paragraph}".strip(),
            "requirement_summary": None,
            "any_satisfies": False,
            "nothing_satisfies_message": not_assessed,
            "ranked": [],
        }
    elif name == "AudienceBrief":
        caveat = (
            "Generated directly from the measurements because the written version was "
            "unavailable; the numbers are the same, the prose is plainer."
        )
        docs = {
            key: {"audience": aud, "title": title, "body": paragraph, "caveat": caveat}
            for key, aud, title in (
                ("planner_memo", "planner", "Measurements"),
                ("lesson_plan", "educator", "What the measurements say"),
                ("public_explainer", "public", "What it is like there"),
            )
        }
        payload = {
            "status": status,
            "reason": reason,
            "site_id": site_id,
            **(docs if facts else {}),
            "shared_numbers": [],
        }
    elif name == "QuestionAnswer":
        payload = {
            "status": status,
            "reason": reason,
            "question": req.get("question"),
            "answer": paragraph or None,
            "rows": [],
            "interpreted_as": "Not interpreted: the written answer was unavailable, so this "
            "lists the measurements that were retrieved.",
        }
    else:
        payload = {
            "status": status,
            "reason": reason,
            "site_id": site_id,
            "paragraph": paragraph or "No data could be retrieved for this request.",
            "numbers_used": [],
        }
    # Validate against the agent's own contract: a fallback that does not fit
    # it is a bug here, and must fail loudly in tests rather than reach a client.
    validated: dict[str, Any] = json.loads(
        spec.output_model.model_validate(payload).model_dump_json()
    )
    return validated


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def _schema_for(model_cls: type[BaseModel]) -> dict[str, Any]:
    """The output contract, in the dialect Gemini accepts.

    Nested models are inlined rather than left as $ref, because the API does
    not resolve them and silently treats an unresolved ref as an empty schema --
    which means no constraint at all on the field that needed it most.
    """
    from app.agents.schema_convert import to_gemini_schema

    return to_gemini_schema(model_cls.model_json_schema())


async def run_agent(
    session: Session,
    spec: AgentSpec,
    user_prompt: str,
    request_payload: dict[str, Any],
    prefetched: list[tools.ToolCallLog] | None = None,
) -> AgentOutcome:
    """Run one agent to a terminal state.

    ``prefetched`` results are put into the grounding pool, not merely into the
    prompt. Leaving them out was a real bug: the explainer handed the model its
    facts in the prompt text, and the guard -- which only ever looks at
    ``call_logs`` -- then saw no tool calls at all and rejected every number in a
    perfectly correct answer as ungrounded. The pool must be exactly what the
    model was told, or the guard is measuring the wrong thing.
    """
    s = get_settings()
    models = list(spec.models or model_chain())
    model = models[0]
    skipped: list[dict[str, Any]] = []
    max_rounds = spec.max_rounds or s.agent_max_rounds
    deadline = time.monotonic() + s.agent_timeout_s
    t0 = time.perf_counter()

    decls = [d for d in tools.TOOL_DECLARATIONS if d["name"] in spec.tool_names]
    opening: list[Any] = [{"role": "user", "parts": [{"text": user_prompt}]}]
    contents: list[Any] = list(opening)
    call_logs: list[tools.ToolCallLog] = list(prefetched or [])
    guard_failures: list[dict[str, Any]] = []
    prompt_tokens = completion_tokens = 0
    attempts = 1

    def remaining() -> float:
        """Time left in the whole budget. Raises once it is spent.

        The old version floored this at half a second, so a run that had
        already used its twenty seconds still made up to six more model calls
        at 0.5 s each: the "hard" limit was soft by three seconds plus however
        long the tools took.
        """
        left = deadline - time.monotonic()
        if left <= 0.0:
            raise DeadlineExceeded(f"agent budget of {s.agent_timeout_s:.0f} s spent")
        return left

    def fallback(status: str, reason: str, detail: str) -> AgentOutcome:
        """A measurement-only answer, checked by the same guard as a written one."""
        result = deterministic_summary(spec, call_logs, detail, request_payload)
        verdict = guards.check(result, tool_dicts_for_guard())
        if not verdict.ok:
            # Built from tool values, so this should be impossible; if it happens
            # the text is withheld rather than shipped unchecked.
            log.error(
                "%s: deterministic summary failed its own guard: %s",
                spec.name,
                "; ".join(v.detail for v in verdict.violations),
            )
            return AgentOutcome(
                status=AgentStatus.ERROR, result=None, reason=reason, attempts=attempts
            )
        return AgentOutcome(
            status=status,
            result=result,
            reason=reason,
            provenance=[_citation(c) for c in verdict.citations],
            attempts=attempts,
        )

    def tool_dicts_for_guard() -> list[dict[str, Any]]:
        return [
            {"seq": 0, "tool": guards.USER_REQUEST_TOOL, "result": request_payload},
            *(c.as_dict() for c in call_logs),
        ]

    async def finish(outcome: AgentOutcome) -> AgentOutcome:
        outcome.latency_ms = (time.perf_counter() - t0) * 1000.0
        outcome.tool_calls = call_logs
        # Models skipped on the way are part of the record, before any
        # rejection by the guard of the model that answered.
        outcome.guard_failures = skipped + guard_failures
        outcome.model = model
        run_id = await record_run(
            session,
            AgentRunRecord(
                agent=spec.name,
                model=model,
                status=outcome.status,
                request=request_payload,
                response=outcome.result,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=outcome.latency_ms,
                attempts=outcome.attempts,
                guard_failures=outcome.guard_failures or None,
                error=outcome.reason if outcome.status == AgentStatus.ERROR else None,
                tool_calls=[
                    ToolCallRecord(
                        seq=c.seq,
                        tool=c.tool,
                        args=c.args,
                        result=c.result,
                        numbers=c.numbers,
                        latency_ms=c.latency_ms,
                        error=c.error,
                    )
                    for c in call_logs
                ],
            ),
        )
        outcome.run_id = str(run_id)
        return outcome

    # --- the model chain --------------------------------------------------
    # Each model gets a clean run: Gemini 3 signs its own function calls, and
    # a conversation begun on one model cannot be continued on another. A
    # model over its quota fails on its first request, so moving on costs one
    # round trip, and it is skipped until its quota resets.
    if not _current().enabled:
        return await finish(
            fallback(
                AgentStatus.DEGRADED,
                "The AI assistant is turned off in Settings, so this summary is generated "
                "directly from the measurements.",
                "The AI assistant is turned off.",
            )
        )

    response: dict[str, Any] | None = None
    try:
        for model in _usable(models):
            contents = list(opening)
            call_logs = list(prefetched or [])
            guard_failures = []
            attempts = 1
            try:
                # --- phase 1: gather -------------------------------------------
                for _round in range(max_rounds):
                    response = await _generate(
                        model,
                        contents,
                        spec.system_prompt,
                        decls,
                        response_schema=None,
                        timeout_s=remaining(),
                    )
                    prompt_tokens += response["prompt_tokens"]
                    completion_tokens += response["completion_tokens"]

                    if not response["function_calls"]:
                        break
                    if len(call_logs) >= s.agent_max_tool_calls:
                        contents.append(
                            {
                                "role": "user",
                                "parts": [{"text": BUDGET_SPENT_PROMPT}],
                            }
                        )
                        break

                    # Tool calls within a round run concurrently; they are independent
                    # reads and the round's latency is then its slowest call, not its sum.
                    # They count against the same deadline as the model calls.
                    pending = response["function_calls"][: s.agent_max_tool_calls - len(call_logs)]
                    results = await asyncio.wait_for(
                        asyncio.gather(
                            *(
                                tools.execute(session, c["name"], c["args"], len(call_logs) + i + 1)
                                for i, c in enumerate(pending)
                            )
                        ),
                        timeout=remaining(),
                    )
                    call_logs.extend(results)
                    # The model's own turn goes back verbatim, thought signatures and
                    # all (ADR-3 amendment). The reconstructed form is only a fallback
                    # for scripted test responses that carry no content object.
                    # Only when every call in the turn is being answered: Gemini expects
                    # one function response per call it made.
                    verbatim = len(pending) == len(response["function_calls"])
                    contents.append(
                        (response.get("model_content") if verbatim else None)
                        or {
                            "role": "model",
                            "parts": [
                                {"function_call": {"name": c["name"], "args": c["args"]}}
                                for c in pending
                            ],
                        }
                    )
                    contents.append(
                        {
                            "role": "user",
                            "parts": [
                                {"function_response": {"name": r.tool, "response": r.result or {}}}
                                for r in results
                            ],
                        }
                    )
                else:
                    return await finish(
                        AgentOutcome(
                            status=AgentStatus.INSUFFICIENT,
                            result=None,
                            reason=(
                                f"The assistant kept requesting data after {max_rounds} rounds "
                                f"without producing an answer. The underlying numbers are "
                                f"available on the site and comparison views."
                            ),
                            attempts=attempts,
                        )
                    )

                # --- phase 2: structured answer, validated, one repair -------------
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"text": ANSWER_NOW_PROMPT}],
                    }
                )
                # The user's own request is a legitimate source of numbers.
                #
                # Echoing "at least 4 hours of Earth contact" back in a requirement
                # summary is quoting, not claiming, and the first version of this guard
                # rejected it -- the advisor could not restate the requirement it was
                # given without failing. The request is added as an explicit pseudo-tool
                # so those numbers are grounded *and* visibly attributed to the user
                # rather than to a measurement, which is the distinction that matters
                # when reading the provenance list.
                tool_dicts = tool_dicts_for_guard()
                last_failure = "grounding"

                for attempt in (1, 2):
                    attempts = attempt
                    response = await _generate(
                        model,
                        contents,
                        spec.system_prompt,
                        [],
                        response_schema=_schema_for(spec.output_model),
                        timeout_s=remaining(),
                    )
                    prompt_tokens += response["prompt_tokens"]
                    completion_tokens += response["completion_tokens"]

                    try:
                        parsed = spec.output_model.model_validate_json(response["text"])
                        payload = json.loads(parsed.model_dump_json())
                    except (ValidationError, ValueError) as exc:
                        last_failure = "schema"
                        guard_failures.append({"kind": "schema_invalid", "detail": str(exc)[:500]})
                        if attempt == 2:
                            break
                        contents.append(
                            {
                                "role": "user",
                                "parts": [
                                    {
                                        "text": (
                                            f"Your reply did not match the schema "
                                            f"({exc}). Reply with JSON matching it exactly."
                                        )
                                    }
                                ],
                            }
                        )
                        continue

                    verdict = guards.check(payload, tool_dicts)
                    if verdict.ok:
                        return await finish(
                            AgentOutcome(
                                status=(
                                    AgentStatus.INSUFFICIENT
                                    if payload.get("status") == "insufficient_data"
                                    else AgentStatus.OK
                                ),
                                result=payload,
                                reason=payload.get("reason"),
                                provenance=[_citation(c) for c in verdict.citations],
                                attempts=attempt,
                            )
                        )

                    last_failure = "grounding"
                    guard_failures.extend(v.as_dict() for v in verdict.violations)
                    log.warning(
                        "%s: guard rejected attempt %d: %s",
                        spec.name,
                        attempt,
                        "; ".join(v.kind for v in verdict.violations),
                    )
                    if attempt == 1:
                        contents.append(
                            {"role": "user", "parts": [{"text": verdict.repair_hint()}]}
                        )

                # Two rejections. Degrade rather than render ungrounded text.
                what = (
                    "did not match the required structure"
                    if last_failure == "schema"
                    else "contained numbers that are not in the data"
                )
                return await finish(
                    fallback(
                        AgentStatus.GUARD_REJECTED,
                        f"The written answer {what} twice, so it was discarded; showing a "
                        "measurement-only summary instead.",
                        f"The written answer {what}, so it was discarded. This summary is "
                        "generated directly from the measurements.",
                    )
                )

            except ModelUnavailable as exc:
                _cool(exc.model, exc.cooldown_s, exc.why)
                log.warning("%s: %s; trying the next model", spec.name, exc)
                skipped.append({"kind": "model_unavailable", "model": exc.model, "detail": exc.why})
                continue

        # No model in the chain could answer: every one is over its quota,
        # not served to this key, or down.
        return await finish(
            fallback(
                AgentStatus.DEGRADED,
                "Every configured model is over its quota or unavailable right now, so this "
                "summary is generated directly from the measurements.",
                "No model could answer right now.",
            )
        )

    except TimeoutError:
        return await finish(
            fallback(
                AgentStatus.TIMEOUT,
                f"The assistant did not finish within {s.agent_timeout_s:.0f} s. Showing a "
                "summary generated directly from the measurements.",
                "The assistant did not respond in time.",
            )
        )
    except GeminiUnavailable as exc:
        return await finish(
            fallback(
                AgentStatus.DEGRADED,
                "The assistant is not configured, so this summary is generated directly "
                "from the measurements.",
                str(exc),
            )
        )
    except Exception as exc:
        log.exception("%s failed", spec.name)
        return await finish(
            fallback(
                AgentStatus.ERROR,
                "The assistant could not complete this request. Showing a summary "
                "generated directly from the measurements.",
                type(exc).__name__,
            )
        )


def _citation(c: guards.Citation) -> dict[str, Any]:
    return {
        "claim": c.claim,
        "value": c.value,
        "tool": c.tool,
        "call_seq": c.call_seq,
        "field": c.field,
    }


async def prefetch(
    session: Session, calls: list[tuple[str, dict[str, Any]]]
) -> list[tools.ToolCallLog]:
    """Run tools before the model sees anything.

    Used by agents whose data needs are known from the request (A1, A3). It
    removes a whole round trip and, more importantly, guarantees the grounding
    pool is populated even if the model never calls a tool itself -- so a
    degraded answer is still a correct one.
    """
    out: list[tools.ToolCallLog] = []
    for i, (name, args) in enumerate(calls, 1):
        out.append(await tools.execute(session, name, args, i))
    return out
