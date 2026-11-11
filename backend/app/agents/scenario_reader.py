"""Scenario reader: plain words into the values a what-if assumes.

"launch on Falcon Heavy in March, 10 days on the surface" becomes a vehicle, a
launch window and a number of days. The model only names things: it picks ids and
dates from ``list_scenario_options`` and copies numbers from the prompt, it works
out nothing, and every value it returns is checked again here against those
options and the prompt before it is used. The same grounding guard as the asker
checks its sentence. Without ``PW_GEMINI_API_KEY`` (or when the model does not
answer) the prompt is read by the rules in ``core.scenario`` and the answer says so.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents import tools
from app.agents.base import AgentOutcome, AgentSpec, AgentStatus, run_agent
from app.agents.tools import Session
from app.config import get_settings
from app.core import scenario as core

SYSTEM = """\
You turn a short what-if request about a lunar mission into the values it names.

Call `list_scenario_options` for the mission first. Then fill `values` with only what
the request says, one entry per field, using these field names:
vehicle_id, pad_id, launch_from, launch_to, landing_date, surface_days, transfer_type,
sun_el_min_deg, sun_el_max_deg, relays.

Rules:
- A vehicle, pad, relay or transfer type is given by its id from the options, never by a
  name you make up. A relay list is comma-separated ids.
- Dates are YYYY-MM-DD and come from the options' `months` (first_day, last_day) or from the
  request itself. "launch in March" is launch_from = that month's first_day and launch_to =
  its last_day. "land in March" is landing_date = that month's first_day. A month with no year
  is the first one in `months`. Never work out a date yourself.
- Numbers (days on the surface, degrees) are copied from the request. If the request gives
  none, leave the field out.
- Do not fill a field the request does not mention, and do not use the mission's published
  values: those are added later.
- Put anything you could not turn into a value in `unresolved`, in a plain sentence.
- `paragraph` is one sentence saying how you read the request.
- Never give a verdict, a score, or a go/no-go, and never say what is likely.
"""


class ReadValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    value: str = Field(description="An id, a YYYY-MM-DD date, or a number as written.")


class ScenarioReading(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["ok", "insufficient_data"]
    reason: str | None = None
    paragraph: str | None = Field(
        default=None, description="One sentence: how the request was read."
    )
    values: list[ReadValue] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    site_id: str | None = None
    numbers_used: list[Any] = Field(default_factory=list)


SPEC = AgentSpec(
    name="scenario_reader",
    system_prompt=SYSTEM,
    tool_names=("list_scenario_options",),
    output_model=ScenarioReading,
    max_rounds=3,
)

_NO_MODEL = "No AI model is configured, so the prompt was read by rules."
_MODEL_FAILED = "The AI model did not give a usable reading, so the prompt was read by rules."


def _names(ctx: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {"vehicles": ctx["vehicles"], "pads": ctx["pads"], "relays": ctx["relays"], "sites": {}}


def sentence(values: dict[str, Any], ctx: dict[str, Any]) -> str:
    if not values:
        return "Nothing in the prompt could be turned into a value."
    nm = _names(ctx)
    parts = [f"{core.SPEC_BY_ID[k].label} {core.display(k, v, nm)}" for k, v in values.items()]
    return "Read as: " + "; ".join(parts) + "."


def by_rules(prompt: str, ctx: dict[str, Any], why: str) -> core.Reading:
    r = core.parse_prompt(
        prompt,
        date.fromisoformat(ctx["today"]),
        vehicles=ctx["vehicles"],
        pads=ctx["pads"],
        relays=ctx["relays"],
    )
    r.method = "rules"
    r.interpreted_as = f"{why} {sentence(core.canonical(r.values), ctx)}"
    return r


def _numbers_in(text: str) -> set[float]:
    return {float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)}


def clean(
    items: list[ReadValue], prompt: str, ctx: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Keep only values that are real options or were in the prompt; the rest are said."""
    nums = _numbers_in(prompt)
    allowed_dates = {ctx["today"]}
    for mth in ctx["months"]:
        allowed_dates |= {mth["first_day"], mth["last_day"]}
    allowed_dates |= set(re.findall(r"\d{4}-\d\d-\d\d", prompt))
    options = {
        "vehicle_id": ctx["vehicles"],
        "pad_id": ctx["pads"],
        "transfer_type": ctx["transfer_types"],
    }
    out: dict[str, Any] = {}
    bad: list[str] = []
    for it in items:
        spec = core.SPEC_BY_ID.get(it.field)
        raw = it.value.strip()
        if spec is None or it.field == "site_id":
            bad.append(f"'{it.field}' was not used: a landing spot is chosen on the form.")
        elif spec.kind == "date":
            if raw in allowed_dates:
                out[it.field] = raw
            else:
                bad.append(f"The date {raw} is not one the request or the calendar names.")
        elif spec.kind == "number":
            try:
                x = float(raw)
            except ValueError:
                bad.append(f"'{raw}' is not a number for {spec.label.lower()}.")
                continue
            if x in nums:
                out[it.field] = x
            else:
                bad.append(
                    f"{x:g} for {spec.label.lower()} is not in the request, so it was not used."
                )
        elif spec.kind == "multi_choice":
            ids = [p.strip() for p in raw.split(",") if p.strip()]
            if ids and all(i in ctx["relays"] for i in ids):
                out[it.field] = sorted(ids)
            else:
                bad.append(f"'{raw}' does not name relays in the list.")
        elif raw in options.get(it.field, {}):
            out[it.field] = raw
        else:
            bad.append(f"'{raw}' is not one of the choices for {spec.label.lower()}.")
    return out, bad


async def context(session: Session, mission_id: str) -> dict[str, Any]:
    """What the request can name for this mission (through the tool surface)."""
    return await tools.scenario_context(session, mission_id)


async def read(
    session: Session, prompt: str, ctx: dict[str, Any], section: str | None = None
) -> core.Reading:
    """Read ``prompt`` for the mission in ``ctx`` (from ``context``)."""
    if not get_settings().agents_enabled:
        return by_rules(prompt, ctx, _NO_MODEL)
    where = f" (about the {section} step)" if section else ""
    out: AgentOutcome = await run_agent(
        session,
        SPEC,
        f"Mission: {ctx['mission_id']}. Today is {ctx['today']}. Request: {prompt}{where}",
        {"question": prompt, "mission_id": ctx["mission_id"], "today": ctx["today"]},
    )
    res = out.result or {}
    if out.status != AgentStatus.OK or res.get("status") != "ok" or not res.get("values"):
        why = (
            _MODEL_FAILED if out.status != AgentStatus.OK else "The AI model found nothing to set."
        )
        return by_rules(prompt, ctx, why)
    values, bad = clean([ReadValue(**v) for v in res["values"]], prompt, ctx)
    if not values or core.validate(values):
        return by_rules(prompt, ctx, _MODEL_FAILED)
    return core.Reading(
        values=values,
        unresolved=[*(res.get("unresolved") or []), *bad],
        method="model",
        interpreted_as=str(res.get("paragraph") or sentence(core.canonical(values), ctx)),
    )
