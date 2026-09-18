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
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import guards, tools
from app.config import get_settings
from app.services.agent_log import AgentRunRecord, ToolCallRecord, record_run

log = logging.getLogger(__name__)


class AgentStatus:
    OK = "ok"
    INSUFFICIENT = "insufficient_data"
    GUARD_REJECTED = "guard_rejected"
    TIMEOUT = "timeout"
    DEGRADED = "degraded"
    ERROR = "error"


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
    model: str | None = None
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


# ---------------------------------------------------------------------------
# Model transport
# ---------------------------------------------------------------------------


class GeminiUnavailable(RuntimeError):
    pass


async def _generate(
    model: str,
    contents: list[dict[str, Any]],
    system_prompt: str,
    tool_decls: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any] | None,
    timeout_s: float,
) -> dict[str, Any]:
    """One call to Gemini via google-genai.

    Isolated behind a function so the whole loop can be exercised offline: the
    tests intercept the SDK's HTTP transport with respx, and nothing above this
    line knows or cares.
    """
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiUnavailable("PW_GEMINI_API_KEY is not set")

    from google import genai
    from google.genai import types as gt

    client = genai.Client(api_key=s.gemini_api_key)
    config: dict[str, Any] = {
        "system_instruction": system_prompt,
        "max_output_tokens": s.agent_max_output_tokens,
        "temperature": 0.2,
    }
    if tool_decls:
        config["tools"] = [gt.Tool(function_declarations=tool_decls)]
    if response_schema is not None:
        config["response_mime_type"] = "application/json"
        config["response_schema"] = response_schema

    def _call() -> Any:
        return client.models.generate_content(
            model=model, contents=contents, config=gt.GenerateContentConfig(**config)
        )

    resp = await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout_s)

    calls: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            fc = getattr(part, "function_call", None)
            if fc is not None:
                calls.append({"name": fc.name, "args": dict(fc.args or {})})
            txt = getattr(part, "text", None)
            if txt:
                text_parts.append(txt)

    usage = getattr(resp, "usage_metadata", None)
    return {
        "function_calls": calls,
        "text": "".join(text_parts),
        "prompt_tokens": int(getattr(usage, "prompt_token_count", 0) or 0),
        "completion_tokens": int(getattr(usage, "candidates_token_count", 0) or 0),
    }


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def deterministic_summary(
    spec: AgentSpec, tool_calls: list[tools.ToolCallLog], reason: str
) -> dict[str, Any]:
    """A correct answer built from tool results alone, with no model involved.

    This is what makes the degrade path real rather than aspirational. If Gemini
    is unreachable, or if it fails the guard twice, the user still gets the four
    numbers -- assembled by a template from values that are grounded by
    construction, and labelled ``degraded`` so nobody mistakes it for the
    written answer.
    """
    facts: list[str] = []
    site_id: str | None = None

    for call in tool_calls:
        r = call.result or {}
        if call.error:
            continue
        site_id = site_id or r.get("site_id")
        if call.tool == "get_metrics":
            facts.append(
                f"Over the requested window this site is sunlit for "
                f"{r.get('sunlit_s', 0) / 3600:.0f} hours "
                f"({r.get('sun_fraction_up', 0) * 100:.0f}% of the window) and has "
                f"Earth in view for {r.get('earth_contact_s', 0) / 3600:.0f} hours "
                f"({r.get('earth_fraction_up', 0) * 100:.0f}%). "
                f"The longest unbroken darkness is {r.get('longest_dark_s', 0) / 3600:.0f} "
                f"hours and the longest unbroken loss of Earth contact is "
                f"{r.get('longest_blackout_s', 0) / 3600:.0f} hours."
            )
        elif call.tool == "get_site":
            facts.append(
                f"{r.get('name', site_id)} sits at {r.get('lat_deg', 0):.3f} degrees "
                f"latitude, {r.get('lon_deg', 0):.3f} degrees east, at an elevation of "
                f"{r.get('elev_m', 0):.0f} m."
            )
        elif call.tool == "get_horizon_profile":
            facts.append(
                f"Its highest skyline is {r.get('max_el_deg', 0):.2f} degrees at a "
                f"bearing of {r.get('max_el_bearing_deg', 0):.0f} degrees."
            )

    paragraph = " ".join(facts) if facts else "No data could be retrieved for this request."
    return {
        "status": "ok" if facts else "insufficient_data",
        "reason": reason,
        "site_id": site_id,
        "paragraph": paragraph,
        "numbers_used": [],
    }


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
    session: AsyncSession,
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
    model = spec.model or s.agent_model
    max_rounds = spec.max_rounds or s.agent_max_rounds
    deadline = time.monotonic() + s.agent_timeout_s
    t0 = time.perf_counter()

    decls = [d for d in tools.TOOL_DECLARATIONS if d["name"] in spec.tool_names]
    contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": user_prompt}]}]
    call_logs: list[tools.ToolCallLog] = list(prefetched or [])
    guard_failures: list[dict[str, Any]] = []
    prompt_tokens = completion_tokens = 0
    attempts = 1

    def remaining() -> float:
        return max(0.5, deadline - time.monotonic())

    async def finish(outcome: AgentOutcome) -> AgentOutcome:
        outcome.latency_ms = (time.perf_counter() - t0) * 1000.0
        outcome.tool_calls = call_logs
        outcome.guard_failures = guard_failures
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
                guard_failures=guard_failures or None,
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

    # --- phase 1: gather ---------------------------------------------------
    response: dict[str, Any] | None = None
    try:
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
                        "parts": [
                            {
                                "text": "Tool call budget exhausted. Answer with what you have, or "
                                "return status='insufficient_data'."
                            }
                        ],
                    }
                )
                break

            # Tool calls within a round run concurrently; they are independent
            # reads and the round's latency is then its slowest call, not its sum.
            pending = response["function_calls"][: s.agent_max_tool_calls - len(call_logs)]
            results = await asyncio.gather(
                *(
                    tools.execute(session, c["name"], c["args"], len(call_logs) + i + 1)
                    for i, c in enumerate(pending)
                )
            )
            call_logs.extend(results)
            contents.append(
                {
                    "role": "model",
                    "parts": [
                        {"function_call": {"name": c["name"], "args": c["args"]}} for c in pending
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
                "parts": [
                    {"text": "Now answer. Respond ONLY with JSON matching the required schema."}
                ],
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
        tool_dicts = [
            {"seq": 0, "tool": guards.USER_REQUEST_TOOL, "result": request_payload},
            *(c.as_dict() for c in call_logs),
        ]

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
            except Exception as exc:
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
                        provenance=[
                            {
                                "claim": c.claim,
                                "value": c.value,
                                "tool": c.tool,
                                "call_seq": c.call_seq,
                                "field": c.field,
                            }
                            for c in verdict.citations
                        ],
                        attempts=attempt,
                    )
                )

            guard_failures.extend(v.as_dict() for v in verdict.violations)
            log.warning(
                "%s: guard rejected attempt %d: %s",
                spec.name,
                attempt,
                "; ".join(v.kind for v in verdict.violations),
            )
            if attempt == 1:
                contents.append({"role": "user", "parts": [{"text": verdict.repair_hint()}]})

        # Two rejections. Degrade rather than render ungrounded text.
        return await finish(
            AgentOutcome(
                status=AgentStatus.DEGRADED,
                result=deterministic_summary(
                    spec,
                    call_logs,
                    "The written answer contained numbers that are not in the data, so "
                    "it was discarded. This summary is generated directly from the "
                    "measurements.",
                ),
                reason="Answer failed the grounding check twice; showing a "
                "measurement-only summary instead.",
                attempts=attempts,
            )
        )

    except TimeoutError:
        return await finish(
            AgentOutcome(
                status=AgentStatus.DEGRADED,
                result=deterministic_summary(
                    spec, call_logs, "The assistant did not respond in time."
                ),
                reason=f"The assistant timed out after {s.agent_timeout_s:.0f} s. "
                "Showing a summary generated directly from the measurements.",
                attempts=attempts,
            )
        )
    except GeminiUnavailable as exc:
        return await finish(
            AgentOutcome(
                status=AgentStatus.DEGRADED,
                result=deterministic_summary(spec, call_logs, str(exc)),
                reason="The assistant is not configured, so this summary is generated "
                "directly from the measurements.",
                attempts=attempts,
            )
        )
    except Exception as exc:
        log.exception("%s failed", spec.name)
        return await finish(
            AgentOutcome(
                status=AgentStatus.DEGRADED,
                result=deterministic_summary(spec, call_logs, f"{type(exc).__name__}"),
                reason="The assistant could not be reached. Showing a summary "
                "generated directly from the measurements.",
                attempts=attempts,
            )
        )


async def prefetch(
    session: AsyncSession, calls: list[tuple[str, dict[str, Any]]]
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
